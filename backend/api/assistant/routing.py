"""Conservative routing: deterministic cases first; ambiguous local requests ask for bounds."""
import re


def requests_field_values(question):
    return bool(re.search(r'帮我.*(?:查|算|找)|请.*(?:查询|计算|统计|给出)|查一下|算一下|温度.*(?:多少|几度)|(?:最热|最冷).*(?:在哪|位置)|[xyz]\s*[=为：:]',question,re.I))


def capability_question(question):
    if requests_field_values(question):
        return False
    subject = re.search(r'你|助手|系统|AgriSeek',question,re.I)
    ability = re.search(r'只能|能否|能不能|是否能|支持|能力|功能|能.*吗|可以.*吗|不(?:知道|支持|能).*吗',question)
    return bool(subject and ability or re.search(r'(?:非?切面|非?剖面|非?断面).*(?:能不能|能否|支持|能.*吗)',question))


def plan(question, position=None, region=None, regions=None):
    q=question.strip()
    if capability_question(q):
        return {'mode':'capability','tools':[]}
    explaining=bool(re.search(r'原理|机理|文献|论文|为什么|为何|是什么',q))
    if re.search(r'明天|后天|预测.*温|未来.*温',q) and not explaining:
        return {'mode':'unsupported','detail':'当前没有未来温度预测能力。'}
    if re.search(r'过去.*(?:小时|天)|历史.*(?:趋势|温度)|持续.*多久|最近.*小时',q) and not explaining:
        return {'mode':'unsupported','detail':'当前没有历史趋势或持续暴露查询工具。'}
    if re.search(r'自动.*(?:开启|关|喷雾)|(?:开启|开到|设为|调到).*(?:分钟|几度)',q):
        return {'mode':'unsupported','detail':'助手不执行设备控制，也没有设备数值处方依据。'}
    field=bool(position or region or regions or re.search(r'这(?:一|个)?(?:帧|刻|位置|点|棚)|当前|现在|此刻|最热|最冷|热点|最高温|最低温|均温|测点|区域|[xyz]\s*[=为：:]',q))
    # A general question about uniformity is a knowledge question, even if it says "最热".
    if explaining and not (position or region or regions) and not re.search(r'当前|现在|此刻|这(?:一|个)?(?:帧|位置|点|棚)|[xyz]\s*[=为：:]',q):
        field=False
    if not (position or region or regions) and re.search(r'论文|文献|研究进展|研究综述|研究成果',q) and not re.search(
            r'这(?:一|个)?(?:帧|位置|点|棚)|测点|传感器|坐标|重建值|[xyz]\s*[=为：:]',q):
        field=False  # "当前有哪些最新论文" asks for literature, not a live frame.
    if not field:
        return {'mode':'knowledge','tools':['search_agri_knowledge']}
    mode='mixed' if re.search(r'为什么|为何|适宜|适温|热害|冷害|原因|解释|风险',q) else 'field'
    if regions is not None:
        return {'mode':mode,'tool':'compare_regions','args':regions,'tools':['compare_regions']}
    if region is not None:
        return {'mode':mode,'tool':'get_region_statistics','args':region,'tools':['get_region_statistics']}
    if re.search(r'区域|前部|后部|前后|前面|后面|这附近',q):
        return {'mode':'clarification','detail':'请提供区域的 x、y、z 上下限，明确前部或后部的范围。'}
    if re.search(r'最热|最冷|热点|最高温|最低温|极值',q) and '测点' not in q:
        return {'mode':mode,'tool':'find_temperature_extrema','args':{},'tools':['find_temperature_extrema']}
    if position is None:
        values={}
        for axis in 'xyz':
            match=re.search(axis+r'\s*(?:=|为|：|:)\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)',q,re.I)
            if match: values[axis]=float(match.group(1))
        if len(values)==3: position=values
    if position is not None:
        return {'mode':mode,'tool':'get_temperature_point','args':position,'tools':['get_temperature_point']}
    if re.search(r'位置|坐标|这个点|这点|点温',q):
        return {'mode':'clarification','detail':'请填写 x、y、z 坐标，或在问题中明确三个坐标值（单位：米）。'}
    if '均温' in q and '测点' not in q:
        return {'mode':mode,'tool':'get_region_statistics','args':{},'tools':['get_region_statistics']}
    return {'mode':mode,'tools':[]}
