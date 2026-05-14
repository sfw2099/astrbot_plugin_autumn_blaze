from .keyword_trigger import KeywordRoute, PermissionLevel

_DEFAULT_KEYWORD_ROUTES: tuple[KeywordRoute, ...] = (
    KeywordRoute(keyword="今日老婆", action="draw_wife"),
    KeywordRoute(keyword="jrlp", action="draw_wife"),
    KeywordRoute(keyword="抽老婆", action="draw_wife"),

    KeywordRoute(keyword="我的老婆", action="show_history"),
    KeywordRoute(keyword="wdlp", action="show_history"),
    KeywordRoute(keyword="抽取历史", action="show_history"),

    KeywordRoute(keyword="强娶", action="force_marry"),
    KeywordRoute(keyword="qiangqu", action="force_marry"),

    KeywordRoute(keyword="关系图", action="show_graph"),
    KeywordRoute(keyword="羁绊图谱", action="show_graph"),
    KeywordRoute(keyword="gxt", action="show_graph"),

    KeywordRoute(keyword="个人关系图", action="show_ego_graph"),
    KeywordRoute(keyword="grgxt", action="show_ego_graph"),

    KeywordRoute(keyword="抽老婆帮助", action="show_help"),
    KeywordRoute(keyword="老婆插件帮助", action="show_help"),
    KeywordRoute(keyword="clpbz", action="show_help"),

    KeywordRoute(keyword="求婚", action="propose_command"),
    KeywordRoute(keyword="qh", action="propose_command"),

    KeywordRoute(keyword="斩红尘", action="sever_ties"),
    KeywordRoute(keyword="zch", action="sever_ties"),

    KeywordRoute(keyword="点鸳鸯", action="dian_yuanyang"),
    KeywordRoute(keyword="dyy", action="dian_yuanyang"),

    KeywordRoute(keyword="换连理", action="swap_bonds"),
    KeywordRoute(keyword="hll", action="swap_bonds"),

    KeywordRoute(keyword="赠予运势", action="give_fortune"),
    KeywordRoute(keyword="zyys", action="give_fortune"),
)
