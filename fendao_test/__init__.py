import asyncio
import re
from heapq import nlargest
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory

from nonebot import MessageSegment
from .create_img import team2pic
from ..basedata import FilePath, ItemID, stage_dict
from ..clanbattle.base import find_item
from ..login import query
from ..util.decorator import check_account_qqid
from ..util.text2img import image_draw
from ..util.tools import load_config, write_config
from .timeaxis import (
    MAX_QUERY,
    type2chinese,
    clanbattle_work,
    MAX_SINGLE_BOSS,
    TimaAxis,
)
from hoshino.typing import CQEvent, HoshinoBot
from hoshino import Service
from hoshino.util import filt_message, pic2b64
from hoshino.modules.priconne import chara
from hoshino.modules.priconne._pcr_data import CHARA_NAME

helpText1 = """
查轴指令帮助：
查轴 [阶段] [类型] [BOSS] [作业序号]

阶段：ABCD，对应公会战的四个阶段
类型：T 代表自动刀，W 代表尾刀，S代表手动刀，填写多个代表都行，留空表示我全要
BOSS：1-5，对应公会战的一至五王
作业序号：花舞作业的序号，如‘A101’

指令示例：
查轴 A 
(查询一阶段的所有作业信息)
查轴 A101 
(详细查询特定作业)
查轴 A S
(查询一阶段的手动作业信息)
查轴 A 1 
(查询一阶段一王的所有作业信息)
查轴 A T 1 
(查询一阶段一王的AUTO刀作业信息)
查轴 A TS 1 
(查询一阶段一王的AUTO刀和手动刀作业信息)
注：指令示例中的空格均不可省略。

=============================================
数据来源于: https://www.caimogu.cc/gzlj.html
""".strip()

helpText2 = """
分刀指令帮助：
分刀 [阶段] [毛分/毛伤] (类型) (BOSS) 
阶段：ABCD，对应公会战的四个阶段，支持跨面，如‘CCD’，和后面boss一一对应，只填写一个默认全是这一阶段
类型：T 代表自动刀，W 代表尾刀，S代表手动刀，填写多个代表都行，留空表示我全要
BOSS：1-5，对应公会战的一至五王，可以‘123’或者‘12’,也可以‘555’,留空表示哪个boss无所谓
作业序号：列表中作业的序号

指令示例：
分刀 A 毛分
(查询一阶段的所有分刀可能，按分数排序)
分刀 A 毛分 T 
(查询一阶段一王的AUTO刀所有分刀可能，按分数排序)
分刀 A 毛分 T 123
(查询一阶段的1,2,3王所有AUTO刀分刀可能，按分数排序)
自动分刀 毛伤
(上号根据你box自动查看你的box做出分刀，会顶号)
自动分刀 毛伤 T
(设置只考虑自动刀，同上)
注：指令示例中的空格均不可省略。

【添加角色黑名单】 + 角色名称
（支持多角色，例如春环环奈，无空格）
【添加角色缺失】 + 角色名称
（支持多角色，例如春环环奈，无空格）
【删除角色黑名单】 + 角色名称
（支持多角色，例如春环环奈，无空格）
【删除角色缺失】 + 角色名称
（支持多角色，例如春环环奈，无空格）
【删除作业黑名单】 + 作业id
【添加作业黑名单】 + 作业id
【查看角色缺失】（查看哪些角色缺失）
【查看角色黑名单】（查看哪些角色是黑名单）
【查看作业黑名单】（查看哪些作业是黑名单）
【清空角色缺失】（清空角色缺失）
【清空角色黑名单】（清空角色黑名单）
【清空作业黑名单】（清空作业黑名单）

=============================================
数据来源于: https://www.caimogu.cc/gzlj.html
""".strip()

user_path = FilePath.data.value / "fendao" / "user"

sv = Service("分刀", enable_on_default=True, help_=f"{helpText1}\n\n{helpText2}")


@sv.on_fullmatch("查轴帮助")
async def help1(bot: HoshinoBot, ev: CQEvent):
    await bot.send(ev, image_draw(helpText1))


@sv.on_fullmatch("分刀帮助")
async def help2(bot: HoshinoBot, ev: CQEvent):
    await bot.send(ev, image_draw(helpText2))


@sv.on_prefix("查轴")
async def query_timeaxis(bot: HoshinoBot, ev: CQEvent):
    content: str = ev.message.extract_plain_text().strip()
    msg = ""

    work_id = content.upper()
    if re.fullmatch(r"[A-Z][A-Z]?\d{3}", work_id):
        try:
            result = clanbattle_work.get_work_by_id(work_id)
        except KeyError:
            await bot.send(ev, f"未找到轴{work_id}")
            return
        info = result["info"]
        msg += f"{work_id[0]}面{work_id[-3]}王作业" + MessageSegment.image(
            pic2b64(
                await team2pic([(work_id, str(result["damage"]), result["unit"])])
            )
        )

        for video in result["video_link"]:
            text = video["text"]
            url = video["url"]
            note = video["note"]
            msg += (
                f"{info}\n相关视频：\n{text}\n{note}\n{url}"
                if note
                else f"{text}\n{url}"
            )
        await bot.send(ev, msg)
        return

    stage = "A"
    dao_type = "STW"
    boss = "12345"

    for arg in content.upper().split():
        if all(kind in "STW" for kind in arg):
            dao_type = arg
        elif arg in stage_dict:
            stage = arg
        elif len(arg) <= 5 and all(number in "12345" for number in arg):
            boss = arg
        else:
            await bot.send(ev, "出现无效参数，爬爬")
            return

    msg += f"{stage}面{type2chinese(dao_type)}作业"

    for single in boss:
        msg += f"\n{single}王作业：\n"
        works = clanbattle_work.get_boss_work(stage, single, dao_type)
        if not works:
            msg += "暂无作业"
            continue
        msg += MessageSegment.image(
            pic2b64(
                await team2pic(
                    [
                        (work_id, str(work["damage"]), work["unit"])
                        for work_id, work in works.items()
                    ],
                    max_query=MAX_SINGLE_BOSS if len(boss) > 1 else MAX_QUERY,
                )
            )
        )

    await bot.send(ev, msg)


@sv.on_prefix("分刀")
async def fen_dao(bot, ev):
    args = ev.message.extract_plain_text().split()
    stage = "A"
    dao_type = "ST"
    arrange = "毛分"
    bosses = []

    for arg in args:
        token = arg.upper()
        if arg in ("毛分", "毛伤"):
            arrange = arg
        elif all(kind in "STW" for kind in token):
            dao_type = token
        elif len(token) <= 3 and all(letter in stage_dict for letter in token):
            stage = token
        elif len(token) <= 3 and all(number in "12345" for number in token):
            bosses = [int(number) for number in token]
        else:
            await bot.send(ev, "出现无效参数，爬爬")
            return

    if len(stage) > 1 and len(stage) != len(bosses):
        await bot.send(ev, "跨阶段分刀时，阶段和王编号需要一一对应")
        return

    black_info = ""
    black_list = [
        _read_blacklist(user_path / str(ev.user_id) / name)
        for name in ("unit_loss.json", "unit_black.json", "work_black.json")
    ]

    if black_list[2]:
        black_info += f"作业黑名单：{str(black_list[2])[1:-1]}\n"

    if black_list[1]:
        names = [CHARA_NAME.get(unit, (str(unit),))[0] for unit in black_list[1]]
        black_info += f"角色黑名单：{str(names)[1:-1]}\n"

    if black_list[0]:
        names = [CHARA_NAME.get(unit, (str(unit),))[0] for unit in black_list[0]]
        black_info += f"角色缺失：{str(names)[1:-1]}\n"

    if black_info:
        await bot.send(ev, black_info)

    dao = TimaAxis(stage, arrange, set_type=dao_type, all_boss=bosses)
    dao.set_black(*black_list)
    result = await dao.fen_dao()
    if isinstance(result, str):
        await bot.send(ev, result)
        return
    if not result:
        await bot.send(ev, "无分刀作业，请检查角色设置和或更新作业网缓存")
        return

    teams = []
    for answer in result:
        entries = []
        for work_id in answer.teamid_list:
            work = clanbattle_work.get_work_by_id(work_id)
            entries.append((work_id, str(work["damage"]), work["unit"]))
        teams.append(entries)

    boss_label = "".join(map(str, bosses))
    msg = f"{stage}面{boss_label}王分刀参考" if bosses else f"{stage}面分刀参考"
    for i, (answer, entries) in enumerate(zip(result, teams), start=1):
        if arrange == "毛伤":
            total = f"伤害总计：{answer.damage}W"
        else:
            score = f"{answer.score:.2f}".rstrip("0").rstrip(".")
            total = f"分数总计：{score}W"
        picture = await team2pic(entries, borrow=True, unit_loss=black_list[0])
        msg += f"\n第{i}种方案，{total}\n{MessageSegment.image(pic2b64(picture))}"

    await bot.send(ev, msg)


def get_json_name(category, label):
    if category == "作业":
        return "work_black.json"
    if label == "缺失":
        return "unit_loss.json"
    return "unit_black.json"


def _read_blacklist(filename):
    values = load_config(filename)
    return values if isinstance(values, list) else []


async def _update_blacklist(bot, ev, filename, items, *, delete):
    values = _read_blacklist(filename)
    if delete:
        values = [value for value in values if value not in items] if items else []
    else:
        for item in items:
            if item not in values:
                values.append(item)

    filename.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=filename.parent) as staging:
        updated = Path(staging) / filename.name
        write_config(updated, values)
        if filename.exists():
            updated.chmod(filename.stat().st_mode & 0o777)
        updated.replace(filename)
    await bot.send(ev, "删除成功" if delete else "设置成功")


async def set_unit_list(bot, ev, filename, delete=False):
    text = re.sub(r"[?？，,_]", "", ev.message.extract_plain_text())
    units, unknown = chara.roster.parse_team(text)
    if unknown:
        _, name, score = chara.guess_id(unknown)
        if score < 70 and not units:
            return
        unknown = filt_message(unknown)
        message = f'无法识别"{unknown}"'
        if score >= 70:
            message += f" 您说的有{score}%可能是{name}"
        await bot.send(ev, message)
        return
    if not units:
        await bot.send(ev, "请后面加角色名", at_sender=True)
        return
    await _update_blacklist(bot, ev, filename, units, delete=delete)


async def set_work_list(bot, ev, filename, delete=False):
    work_id = ev.message.extract_plain_text().strip().upper()
    if not work_id:
        await bot.send(ev, "请后面加作业id", at_sender=True)
        return
    await _update_blacklist(bot, ev, filename, [work_id], delete=delete)


@sv.on_prefix("添加角色缺失")
@sv.on_prefix("添加作业黑名单")
@sv.on_prefix("添加角色黑名单")
async def set_black(bot, ev):
    name1, name2 = ev.prefix[2:4], ev.prefix[4:6]
    filename = user_path / str(ev.user_id) / get_json_name(name1, name2)
    if name1 == "作业":
        await set_work_list(bot, ev, filename)
    else:
        await set_unit_list(bot, ev, filename)


@sv.on_prefix("删除角色黑名单")
@sv.on_prefix("删除角色缺失")
@sv.on_prefix("删除作业黑名单")
async def delete_black(bot, ev):
    name1, name2 = ev.prefix[2:4], ev.prefix[4:6]
    if not ev.message.extract_plain_text().strip():
        await bot.send(ev, "请后面加作业id/角色名", at_sender=True)
        return
    filename = user_path / str(ev.user_id) / get_json_name(name1, name2)
    if name1 == "作业":
        await set_work_list(bot, ev, filename, delete=True)
    else:
        await set_unit_list(bot, ev, filename, delete=True)


@sv.on_rex(r"^清空(角色|作业)(缺失|黑名单)$")
async def clean_black(bot: HoshinoBot, ev: CQEvent):
    match = ev["match"]
    filename = user_path / str(ev.user_id) / get_json_name(match.group(1), match.group(2))
    await _update_blacklist(bot, ev, filename, [], delete=True)


@sv.on_rex(r"^查看(角色|作业)(缺失|黑名单)$")
async def query_black(bot, ev):
    match = ev["match"]
    filename = user_path / str(ev.user_id) / get_json_name(match.group(1), match.group(2))
    if config := _read_blacklist(filename):
        await bot.send(ev, str(config)[1:-1])
    else:
        await bot.send(ev, f"你没有设置过{match.group(1)}{match.group(2)}")


@sv.scheduled_job("interval", minutes=60)
@sv.on_fullmatch("更新作业网缓存")
async def renew_worklist(bot: HoshinoBot = None, ev: CQEvent = None):
    check = await clanbattle_work.get_clanbattlework()
    if bot and ev:
        await bot.send(ev, "更新作业网缓存成功" if check else "刷新失败，可能是网络问题或者作业网此时没作业")


async def get_proper_team(knife: int, box=None, boss=(1, 2, 3, 4, 5), stage=4, axistype=(1, 2)) -> str:
    bosses = (boss,) if isinstance(boss, int) else boss
    stages = (stage,) if isinstance(stage, int) else stage
    types = (axistype,) if isinstance(axistype, int) else axistype
    dao_type = "".join("STW"[kind - 1] for kind in types)
    works = {}
    for phase in stages:
        for target in bosses:
            works.update(clanbattle_work.get_boss_work(str(phase), target, dao_type))
    if not works:
        return "无推荐配刀"

    solver = TimaAxis(stage_dict[stages[0]], "毛伤")
    solver.set_black()
    if box is not None:
        solver.box = set(box)
    candidates = solver.get_work_list(works)
    checked = (solver.check_available(team) for team in combinations(candidates, knife))
    valid_teams = (result[1] for result in checked if result[0])
    teams = await asyncio.to_thread(nlargest, 6, valid_teams, key=lambda team: team.damage)
    if not teams:
        return "无推荐配刀"

    plans = []
    for team in teams:
        lines = []
        for work_id in team.teamid_list:
            work = works[work_id]
            names = " ".join(chara.fromid(unit).name for unit in work["unit"])
            lines.append(f'{work_id:<5s} {work["damage"]:5d}w {names}')
        plans.append("\n".join(lines))

    separator = "\n\n" if knife > 1 else "\n"
    example = teams[0].teamid_list[0]
    return f'自动配刀：\n{separator.join(plans)}\n\n发送“查轴[轴号]”以获取链接等详细信息。例：查轴{example}'


async def _get_clan_battle_info(account, boss, stage, worktype) -> str:
    try:
        client = await query(account)
        home = await client.home_index()
        clan_id = home.user_clan.clan_id if home.user_clan else None
        if not clan_id:
            return "该账号尚未加入公会"
        index = await client.load_index()
        coin = find_item(index.item_list, ItemID.clanbattle_coin.value)
        info = await client.clan_battle_top(clan_id, coin)
    except Exception:
        sv.logger.exception("自动配刀读取公会战信息失败")
        return "读取公会战信息失败，请稍后重试"

    if info.point is None or info.remaining_count is None:
        return "当前无法获取公会战体力或出刀次数"

    total = info.point // 300
    used = {unit_id // 100 for unit_id in info.used_unit or []}
    used_names = " ".join(chara.fromid(unit_id).name for unit_id in sorted(used))
    lines = [
        f"今日体力点：{info.point}/900",
        f"未出整刀数：{info.remaining_count}刀/共{total}刀",
        f"已用角色：{used_names or '无'}",
    ]
    if info.using_unit:
        names = " ".join(chara.fromid(unit_id // 100).name for unit_id in info.using_unit)
        seconds = info.carry_over_time if info.carry_over_time is not None else "未知"
        lines.extend([f"补偿刀：{seconds}秒", f"补偿角色：{names}"])
    else:
        lines.append("补偿刀：无")

    knife_left = max(0, min(3, info.remaining_count + 3 - total))
    if knife_left:
        owned = {unit.id // 100 for unit in index.unit_list or [] if unit.id}
        lines.append(await get_proper_team(knife_left, owned - used, boss, stage, worktype))
        lines.append("发送“自动配刀帮助”获取详细筛选方式")
    return "\n".join(lines)


team_match_auto_help_str = '''
自动获取该账号今日当前可用角色（会上号）。
随后给出可选配刀组合，按伤害降序排序，输出前6套。
可以按boss号、周目、刀型筛选。

指令：
# 自动配刀
# 自动配刀@somebody
# 自动配刀@somebody [boss号] [周目] [刀型]

boss号：默认为12345
周目：默认为4（D面）
刀型：默认为12（1为手动刀，2为auto刀，3为尾刀）

例：查询ellye当前可出的，目标boss为D2D3的尾刀轴：
# 自动配刀@ellye 23 4 3
'''.strip()


@sv.on_prefix(("自动配刀帮助"))
async def team_match_auto_help(bot, ev):
    await bot.send(ev, team_match_auto_help_str)


def get_team_match_params(args):
    if len(args) > 3:
        raise ValueError("筛选参数过多")
    filters = ["12345", "4", "12"]
    filters[:len(args)] = args
    values = []
    for token, allowed in zip(filters, ("12345", "1234", "123")):
        if not token or any(number not in allowed for number in token):
            raise ValueError("无效筛选参数")
        values.append(sorted({int(number) for number in token}))
    boss, stage, worktype = values
    stages = "".join(stage_dict[phase] for phase in stage)
    bosses = "".join(map(str, boss))
    types = "/".join(("手动", "auto", "尾")[kind - 1] for kind in worktype)
    return boss, stage, worktype, f"筛选{stages}面{bosses}号boss的{types}刀"


team_match_help_str = '''
根据指定给出可选配刀组合，按伤害降序排序，输出前6套。

指令：
配刀 [刀数] [boss号] [周目] [刀型]
boss号：1~5 周目：1~4
刀型：1为手动刀，2为auto刀，3为尾刀

例：查询C面三刀组合阵容：
配刀 3 12345 3 12
'''.strip()


@sv.on_prefix(("配刀帮助"))
async def team_match_help(bot, ev):
    await bot.send(ev, team_match_help_str)


@sv.on_prefix("配刀")
async def get_team_match(bot, ev):
    args = ev.message.extract_plain_text().split()
    try:
        knife = max(1, min(3, int(args[0])))
        boss, stage, worktype, summary = get_team_match_params(args[1:])
    except (IndexError, ValueError):
        await bot.send(ev, f"参数错误！\n\n{team_match_help_str}")
        return
    result = await get_proper_team(knife, None, boss, stage, worktype)
    await bot.send(ev, f'{summary} {knife}刀组合\n{result}\n发送“配刀帮助”获取详细筛选方式')


@sv.on_prefix("#自动配刀", "# 自动配刀")
@check_account_qqid
async def get_team_match_auto(bot, ev, account, qq_id):
    args = ev.message.extract_plain_text().split()
    try:
        boss, stage, worktype, summary = get_team_match_params(args)
    except ValueError:
        await bot.send(ev, f"参数错误！\n\n{team_match_auto_help_str}")
        return
    result = await _get_clan_battle_info(account, boss, stage, worktype)
    await bot.send(ev, f"{account.name or '已绑定账号'}\n{summary}\n{result}")
