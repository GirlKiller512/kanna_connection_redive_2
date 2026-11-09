import re
from pathlib import Path
from tempfile import TemporaryDirectory

from nonebot import MessageSegment
from .create_img import team2pic
from ..util.text2img import image_draw
from ..util.tools import load_config, write_config
from ..basedata import FilePath, stage_dict
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

    if re.match(r"^[A-Za-z][A-Za-z]?\d{3}$", content):
        work_id = content
        result = clanbattle_work.get_work_by_id(content)
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

    args = content.split()
    for arg in args:
        if arg.upper() in stage_dict:
            stage = arg
        elif "".join(sorted(arg.upper())) in dao_type:  # 是否包含，先排序(忽略顺序)
            dao_type = arg
        elif "".join(sorted(arg.upper())) in boss:
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


async def get_proper_team(knife: int, box: set = None, boss=[1, 2, 3, 4, 5], stage=4, axistype=[1, 2]) -> str:
    '''
    剩余刀数 
    可用box set(int)
    筛选：boss(int|list[int]) 周目(int|list[int]) 轴类型（手动/auto/尾刀）(int|list[int])
    '''

    # 简要流程（不考虑补偿刀尾刀）
    if box == None:
        box = set([i for i in range(1000, 2000)])
    box = set(box)

    from .clanbattle_timeaxis import get_timeaxis
    battle_array = await get_timeaxis(boss, stage, axistype)
    # [
    #     {
    #         "sn": "A107",
    #         "units": [int],
    #         "damage": int,
    #         "videos": [
    #             {"text":str, "url":str, "note":str},
    #             {...}
    #         ]
    #     },
    #     {
    #         ...
    #     }
    # ]

    def same_chara(x, y):
        return 10 - len(x | y)

    def have_chara(x):
        return len(x & box)

    def have_84(x, y):
        return have_chara(x) >= 8 and have_chara(y) >= 4

    proper_team = []

    battle_array_set = []
    for homework in battle_array:
        battle_array_set.append(set(homework["units"]))

    cnt = len(battle_array)

    if knife == 1:  # 剩1刀没出
        for i in range(cnt):
            x = battle_array_set[i]
            if have_chara(x) >= 4:  # 五个角色里有4个可用即可
                proper_team.append([i])
    elif knife == 2:  # 剩2刀没出
        for i in range(cnt - 1):
            x = battle_array_set[i]
            for j in range(i + 1, cnt):
                y = battle_array_set[j]
                if same_chara(x, y) == 0:  # 如果没有重复
                    if have_chara(x) >= 4 and have_chara(y) >= 4:  # 这两队中每队的5个角色要有4个
                        proper_team.append([i, j])
                elif same_chara(x, y) <= 2:  # 有1~2个重复
                    if have_chara(x | y) >= 8:  # 这两队中出现的角色要有8个
                        proper_team.append([i, j])

    elif knife == 3:  # 剩3刀没出
        for i in range(cnt - 2):
            x = battle_array_set[i]
            for j in range(i + 1, cnt - 1):
                y = battle_array_set[j]
                for k in range(j + 1, cnt):
                    z = battle_array_set[k]

                    jxy, jyz, jxz = same_chara(x, y), same_chara(
                        y, z), same_chara(x, z)  # 获取两两之间重复角色
                    if jxy < 3 and jyz < 3 and jxz < 3 and jxy + jxz + jyz <= 3:
                        # print("无冲，接下来判断当前账号是否可用")
                        if jxy + jxz + jyz == 3:  # 210/111
                            if set(x | y | z).issubset(box):  # 三队中出现的所有角色都要有
                                proper_team.append([i, j, k])
                        elif (jxy == 0) + (jxz == 0) + (jyz == 0) == 2:  # 200/100
                            # 重复的两队有8个角色 另一队有4个
                            if jxy and have_84(x | y, z) or jxz and have_84(x | z, y) or jyz and have_84(y | z, x):
                                proper_team.append([i, j, k])
                        elif jxy + jxz + jyz == 0:  # 000
                            if have_chara(x) >= 4 and have_chara(y) >= 4 and have_chara(z) >= 4:  # 每队有4个
                                proper_team.append([i, j, k])
                        else:  # 110:
                            if have_chara(x | y | z) >= 12:  # 三队中出现的所有角色（13个）要有任意12个
                                proper_team.append([i, j, k])

    import heapq
    proper_team = heapq.nlargest(6, proper_team, lambda x: sum(
        [battle_array[y]["damage"] for y in x]))
    # proper_team = sorted(proper_team, key=lambda x: sum([battle_array[y]["damage"] for y in x]), reverse=True)

    proper_team_str = []
    sn2videostr = {}
    for team_indexs in proper_team:  # [i,j]
        team_str = []
        for team_index in team_indexs:  # i
            team_info = battle_array[team_index]  # {}
            team_str.append(
                f'{team_info["sn"]:<5s} {team_info["damage"]:5d}w {" ".join([chara.fromid(unit).name for unit in team_info["units"]])}')
            # for video in team_info["videos"]:
            #     team_str.append(f'{video["text"]} {video["url"]} {video["note"]}')
            # if team_info["sn"] not in sn2videostr:
            #     videostr = []
            #     for video in team_info["videos"]:
            #         videostr.append(f'{video["text"]} {video["url"]} {video["note"]}')
            #     sn2videostr[team_info["sn"]] = '\n'.join(videostr)
        proper_team_str.append('\n'.join(team_str))

    # proper_team_videostr = []
    # for sn, videostr in sn2videostr.items():
    #     if '\n' in videostr:
    #         proper_team_videostr.append(f'{sn:<5s}\n{videostr}')
    #     else:
    #         proper_team_videostr.append(f'{sn:<5s} {videostr}')
    #
    # team_outp = '\n\n'.join(proper_team_str)
    # video_outp = '\n'.join(proper_team_videostr)
    # with open(join(curpath, "timeline_status_temp.txt"), "w", encoding='utf-8') as fp:
    #     print(f'自动配刀：\n{team_outp}\n\n阵容信息：\n{video_outp}', file=fp)
    # return team_outp, video_outp

    team_outp = ('\n\n' if (knife > 1) else "\n").join(proper_team_str)

    # with open(join(curpath, "timeline_status_temp.txt"), "w", encoding='utf-8') as fp:
    #    print(f'自动配刀：\n{team_outp}', file=fp)

    if len(team_outp):
        return f'自动配刀：\n{team_outp}\n\n发送“查轴[轴号]”以获取链接等详细信息。例：查轴{battle_array[proper_team[0][0]]["sn"]}'
    else:
        return '无推荐配刀'


@sv.on_prefix("查轴")
async def get_timeline_detail_info(bot, ev):
    from .clanbattle_timeaxis import get_timeaxis
    battle_array = await get_timeaxis()
    sn = ev.message.extract_plain_text().strip()
    battle_array = list(filter(lambda x: x["sn"] == sn, battle_array))

    if len(battle_array):
        battle_array = battle_array[0]
        await bot.send(ev, f'{battle_array["sn"]:<5s} {battle_array["damage"]:5d}w {" ".join([chara.fromid(unit).name for unit in battle_array["units"]])}' + '\n'.join([f'{video["text"]} {video["url"]}{(chr(10) + video["note"] + chr(10)) if len(video["note"]) else ""}' for video in battle_array["videos"]]))
    else:
        await bot.send(ev, f'未找到轴{sn}')


async def _get_clan_battle_info(account_info, boss, stage, worktype) -> str:
    try:
        info = await query.get_clan_battle_info(account_info)
    except Exception as e:
        return f'Fail. {e}'
    else:
        s = []
        s.append(f'今日体力点：{info.get("point", "unknown")}/900')
        s.append(
            f'未出整刀数：{info.get("remaining_count", "unknown")}刀/共{info.get("point", 900)//300}刀'
        )

        knife_left = info.get("remaining_count", 0) + 3 - \
            info.get("point", 900) // 300
        used_unit_id = info.get("used_unit", [])

        used_unit_str = " ".join(
            [chara.fromid(int(unit) // 100).name for unit in used_unit_id])
        s.append(f'已用角色：{used_unit_str if used_unit_str != "" else "无"}')

        using_unit_id = info.get("using_unit", [])
        using_unit_str = " ".join(
            [chara.fromid(int(unit) // 100).name for unit in using_unit_id])
        if using_unit_str == "":
            s.append(f'补偿刀：无')
        else:
            s.append(f'补偿刀：{info.get("carry_over_time", "unknown")}秒')
            s.append(f'补偿角色：{using_unit_str}')

        s = '\n'.join(s)
        if knife_left:
            from ...autobox import _get_box_id_list_from_pcrid
            user_box = set(_get_box_id_list_from_pcrid(account_info["pcrid"]))
            # print(f'该账号拥有的角色\n{user_box}')
            used_box = set(int(uid) // 100 for uid in used_unit_id)
            # print(f'今日出刀已用角色 {used_unit_str}\n{used_box}')
            avail_box = user_box - used_box
            # print(f'该账号当前实际可用角色\n{avail_box}')
            if len(avail_box):
                team_str = await get_proper_team(knife_left, avail_box, boss, stage, worktype)
                return f'{s}\n{team_str}\n发送“自动配刀帮助”获取详细筛选方式'

        return s

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


async def get_team_match_params(bot, ev):
    msg = ev.message.extract_plain_text().strip().split()

    def preprocess(st: str, mi: int, ma: int):
        lis = list(sorted(list(set([int(i) if i.isdigit() and int(
            i) >= mi and int(i) <= ma else 0 for i in st]) - set([0]))))
        return lis if len(lis) else [i for i in range(mi, ma + 1)]
    boss = [1, 2, 3, 4, 5]
    stage = [4]
    worktype = [1, 2]
    stagename = {1: 'A', 2: 'B', 3: 'C', 4: 'D'}
    worktypename = {1: "手动", 2: "auto", 3: "尾"}
    if len(msg) >= 3:
        boss = preprocess(msg[-3], 1, 5)
        stage = preprocess(msg[-2], 1, 4)
        worktype = preprocess(msg[-1], 1, 3)
    # elif len(msg) == 2:
    #     await bot.send(ev, f"参数数量错误！\n\n{team_match_auto_help_str}")
    #     raise RuntimeError("Number of Params Error")
    ss = f'筛选{"".join([stagename[k] for k in stage])}面{"".join([str(l) for l in boss])}号boss的{"/".join([worktypename[j] for j in worktype])}刀'
    return boss, stage, worktype, ss

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


@sv.on_prefix(("配刀"))
async def get_team_match(bot, ev):
    try:
        knife = max(
            1, min(3, int(ev.message.extract_plain_text().strip().split()[0])))
    except:
        await bot.send(ev, f'参数错误！\n\n{team_match_help_str}')
    boss, stage, worktype, ss = await get_team_match_params(bot, ev)
    ss = ss.strip() + f' {knife}刀组合'
    ret = await get_proper_team(knife, None, boss, stage, worktype)
    await bot.send(ev, f'{ss}\n{ret}\n发送“配刀帮助”获取详细筛选方式')


@sv.on_prefix(("#自动配刀"))
# 自动配刀<@人> 不ata默认自己
async def get_team_match_auto(bot, ev):
    try:
        account_info, qqid, nam = await get_target_account(bot, ev, True)
    except:
        return

    boss, stage, worktype, ss = await get_team_match_params(bot, ev)
    clan_battle_info = await _get_clan_battle_info(account_info, boss, stage, worktype)
    await bot.send(ev, f'{nam}\n{ss}\n{clan_battle_info}')
