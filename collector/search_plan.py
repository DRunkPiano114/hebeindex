"""
search_plan.py — Declarative search configuration.

Every search query previously embedded in prompts.py INITIAL_TASK is now a
plain data structure.  The pipeline executes them deterministically — no LLM
needed to dispatch searches.
"""

from __future__ import annotations

SEARCH_PLAN: list[dict] = [
    # ------------------------------------------------------------------
    # File 1: README.md  (no searches — written from a static template)
    # ------------------------------------------------------------------
    {
        "file_id": 1,
        "output_path": "README.md",
        "title": "田馥甄（Hebe）内容资料库",
        "description": "总目录、田馥甄基本信息、所有官方平台账号链接、文件索引。",
        "searches": [],
    },
    # ------------------------------------------------------------------
    # File 2: 个人MV完整列表
    # ------------------------------------------------------------------
    {
        "file_id": 2,
        "output_path": "MV/个人MV.md",
        "title": "田馥甄个人 MV 完整列表",
        "description": "按专辑分组，每首MV一行，含：歌名、链接、平台、发布日期、播放量、导演/频道、简介。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 MV official"},
            {"tool": "youtube", "query": "Hebe Tien MV official"},
            {"tool": "youtube", "query": "田馥甄 LOVE! MV"},
            {"tool": "youtube", "query": "田馥甄 寂寞寂寞就好 MV"},
            {"tool": "youtube", "query": "田馥甄 还是要幸福 MV"},
            {"tool": "youtube", "query": "田馥甄 魔鬼中的天使 MV"},
            {"tool": "youtube", "query": "田馥甄 渺小 MV"},
            {"tool": "youtube", "query": "田馥甄 不醉不会 MV"},
            {"tool": "youtube", "query": "田馥甄 爱着爱着就永远 MV"},
            {"tool": "youtube", "query": "田馥甄 人间烟火 MV"},
            {"tool": "youtube", "query": "田馥甄 余波荡漾 MV"},
            {"tool": "youtube", "query": "田馥甄 独善其身 MV"},
            {"tool": "youtube", "query": "田馥甄 灵魂伴侣 MV"},
            {"tool": "youtube", "query": "Hebe Tien 小幸运 MV"},
            {"tool": "youtube", "query": "田馥甄 悬日 MV"},
            {"tool": "youtube", "query": "田馥甄 皆可 MV"},
            {"tool": "youtube", "query": "田馥甄 一一 MV"},
            {"tool": "youtube", "query": "田馥甄 无人知晓 MV"},
            {"tool": "youtube", "query": "田馥甄 底里歇斯 MV"},
            {"tool": "youtube", "query": "田馥甄 日常 MV"},
            {"tool": "youtube", "query": "田馥甄 超级玛丽 MV"},
            {"tool": "youtube", "query": "田馥甄 无事生非 MV"},
            {"tool": "youtube", "query": "田馥甄 花花世界 MV"},
            {"tool": "youtube", "query": "田馥甄 无常 MV"},
            {"tool": "youtube", "query": "田馥甄 口袋的温度 MV"},
            # To Hebe (2010) 专辑深度曲
            {"tool": "youtube", "query": "田馥甄 你就不要想起我 MV"},
            {"tool": "youtube", "query": "田馥甄 我对不起我 MV"},
            {"tool": "youtube", "query": "田馥甄 To Hebe MV"},
            # My Love (2011) 专辑深度曲
            {"tool": "youtube", "query": "田馥甄 请你给我好一点的情敌 MV"},
            {"tool": "youtube", "query": "田馥甄 你太猖狂 MV"},
            {"tool": "youtube", "query": "田馥甄 My Love MV"},
            {"tool": "youtube", "query": "田馥甄 妳 MV"},
            # 日常 (2016) 专辑深度曲
            {"tool": "youtube", "query": "田馥甄 无用 MV"},
            {"tool": "youtube", "query": "田馥甄 念念有词 MV"},
            # 无人知晓 (2020) 专辑深度曲
            {"tool": "youtube", "query": "田馥甄 先知 MV official"},
            {"tool": "youtube", "query": "田馥甄 或是一首歌 MV"},
            {"tool": "youtube", "query": "田馥甄 田 MV"},
            {"tool": "youtube", "query": "田馥甄 人什么的最麻烦了 MV"},
            {"tool": "youtube", "query": "田馥甄 讽刺的情书 MV"},
            # 近年独立单曲 MV
            {"tool": "youtube", "query": "田馥甄 一周的朋友 MV"},
            {"tool": "youtube", "query": "田馥甄 乘着无人光影的远行 MV"},
            {"tool": "youtube", "query": "田馥甄 一二三 MV"},
            {"tool": "bilibili", "query": "田馥甄 MV 官方"},
            {"tool": "bilibili", "query": "Hebe 田馥甄 MV"},
            {"tool": "bilibili", "query": "田馥甄 小幸运 官方"},
            # 补充遗漏 MV（渺小/必娶女人 OST，To Hebe 专辑）
            {"tool": "youtube", "query": "田馥甄 我想我不会爱你 MV"},
            {"tool": "youtube", "query": "田馥甄 终身大事 MV"},
            {"tool": "bilibili", "query": "田馥甄 我想我不会爱你 MV"},
            # 渺小 (2013) 专辑遗漏曲目（渺小紀錄影音 DVD 收录8首MV）
            {"tool": "youtube", "query": "田馥甄 矛盾 MV"},
            {"tool": "youtube", "query": "田馥甄 烏托邦 MV"},
            {"tool": "youtube", "query": "田馥甄 离岛 MV"},
            # To Hebe (2010) 专辑遗漏曲目（影音館收录6首MV）
            {"tool": "youtube", "query": "田馥甄 看我的 MV"},
            {"tool": "youtube", "query": "田馥甄 给小孩 MV 林宥嘉"},
            # My Love (2011) 专辑遗漏曲目
            {"tool": "youtube", "query": "田馥甄 要说什么 MV"},
            # 日常 (2016) 专辑遗漏曲目（共11首，此前仅搜8首）
            {"tool": "youtube", "query": "田馥甄 什么哪里 MV"},
            {"tool": "youtube", "query": "田馥甄 慢舞 MV"},
            {"tool": "youtube", "query": "田馥甄 身体都知道 MV"},
            # 无人知晓 (2020) 专辑遗漏曲目（共10首，此前仅搜9首）
            {"tool": "youtube", "query": "田馥甄 影子的影子 MV"},
            # 独立单曲与影视OST正式 MV
            {"tool": "youtube", "query": "田馥甄 现在是什么时辰了 MV"},
            {"tool": "youtube", "query": "田馥甄 自己的房间 MV"},
            {"tool": "youtube", "query": "田馥甄 墨绿的夜 MV"},
            {"tool": "youtube", "query": "田馥甄 不晚 MV"},
            {"tool": "youtube", "query": "田馥甄 最暖的忧伤 MV"},
            {"tool": "youtube", "query": "田馥甄 看淡 MV"},
            {"tool": "youtube", "query": "田馥甄 爱了很久的朋友 MV"},
            # 重点 MV B站补充
            {"tool": "bilibili", "query": "田馥甄 魔鬼中的天使 MV"},
            {"tool": "bilibili", "query": "田馥甄 还是要幸福 MV"},
            {"tool": "bilibili", "query": "田馥甄 渺小 MV"},
            {"tool": "bilibili", "query": "田馥甄 寂寞寂寞就好 MV"},
        ],
    },
    # ------------------------------------------------------------------
    # File 3: 单曲与影视歌
    # ------------------------------------------------------------------
    {
        "file_id": 3,
        "output_path": "歌曲与合作/影视单曲.md",
        "title": "田馥甄影视歌曲与单曲",
        "description": "影视主题曲、官方数字单曲等非专辑收录作品。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 小幸运 我的少女时代"},
            {"tool": "youtube", "query": "Hebe A Little Happiness"},
            {"tool": "youtube", "query": "田馥甄 爱了很久的朋友 后来的我们"},
            {"tool": "youtube", "query": "田馥甄 看淡 一把青"},
            {"tool": "youtube", "query": "田馥甄 自己的房间 Live in Life"},
            {"tool": "youtube", "query": "田馥甄 现在是什么时辰了"},
            {"tool": "youtube", "query": "田馥甄 不晚 深夜食堂"},
            {"tool": "youtube", "query": "田馥甄 墨绿的夜"},
            {"tool": "youtube", "query": "田馥甄 美女与野兽 井柏然"},
            {"tool": "youtube", "query": "田馥甄 爱的预告 MV"},
            {"tool": "youtube", "query": "田馥甄 热情 护舒宝"},
            {"tool": "youtube", "query": "田馥甄 姐 MV 追婚日记"},
            {"tool": "youtube", "query": "田馥甄 十万嬉皮"},
            {"tool": "youtube", "query": "田馥甄 最暖的忧伤 MV"},
            {"tool": "youtube", "query": "田馥甄 先知 怪胎 MV"},
            # 早期影视插曲（维基确认存在，非个人专辑收录）
            {"tool": "youtube", "query": "田馥甄 摩天轮 真命天女"},
            {"tool": "youtube", "query": "田馥甄 来不及 斗牛要不要"},
            # 近年影视单曲
            {"tool": "youtube", "query": "田馥甄 一周的朋友 电影主题曲"},
            {"tool": "bilibili", "query": "田馥甄 小幸运"},
            {"tool": "bilibili", "query": "田馥甄 影视歌曲"},
            # 梦想的声音 翻唱数字单曲（2016-12-14 至 2017-02-22 官方发行，维基确认共8首）
            {"tool": "youtube", "query": "田馥甄 黑色柳丁 单曲 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 凡人歌 火 单曲 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 痒 单曲 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 Play我呸 单曲 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 演员 薛之谦 单曲 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 无与伦比的美丽 阿飞的小蝴蝶 单曲"},
            {"tool": "youtube", "query": "田馥甄 当你 单曲 梦想的声音 巅峰歌会"},
            {"tool": "youtube", "query": "田馥甄 追梦人 单曲 梦想的声音 巅峰歌会"},
            # 影视/独立单曲（皆可/口袋的温度/我想我不会爱你/近年单曲）
            {"tool": "youtube", "query": "田馥甄 皆可 庆余年 主题曲"},
            {"tool": "youtube", "query": "田馥甄 我想我不会爱你 必娶女人 OST"},
            {"tool": "youtube", "query": "田馥甄 口袋的温度 爱上两个我 OST"},
            {"tool": "youtube", "query": "田馥甄 乘着无人光影的远行 2023"},
            {"tool": "youtube", "query": "田馥甄 一二三 2025 田调"},
            {"tool": "bilibili", "query": "田馥甄 梦想的声音 单曲 数字发行"},
            {"tool": "bilibili", "query": "田馥甄 皆可 庆余年"},
            # 飞鱼高校生 OST（维基确认餘波盪漾收录于飛魚高校生電視原聲帶，2016）
            {"tool": "youtube", "query": "田馥甄 余波荡漾 飞鱼高校生 OST"},
            {"tool": "bilibili", "query": "田馥甄 余波荡漾 飞鱼高校生"},
            # 创作非自唱出圈曲目
            {"tool": "youtube", "query": "动力火车 爱到疯癫"},
        ],
    },
    # ------------------------------------------------------------------
    # File 4: 演唱会视频
    # ------------------------------------------------------------------
    {
        "file_id": 4,
        "output_path": "演唱会/演唱会.md",
        "title": "田馥甄演唱会视频",
        "description": "个人演唱会 + S.H.E 历代演唱会，区分官方影像、现场录像、精彩片段。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 如果演唱会 live"},
            {"tool": "youtube", "query": "Hebe If Only concert"},
            {"tool": "youtube", "query": "田馥甄 一一演唱会"},
            {"tool": "youtube", "query": "田馥甄 演唱会 full"},
            {"tool": "youtube", "query": "田馥甄 To Hebe 音乐会"},
            {"tool": "youtube", "query": "田馥甄 小巨蛋"},
            {"tool": "youtube", "query": "田馥甄 IF ONLY 演唱会"},
            {"tool": "bilibili", "query": "田馥甄 演唱会 全场", "page": 1},
            {"tool": "bilibili", "query": "田馥甄 演唱会 全场", "page": 2},
            {"tool": "bilibili", "query": "如果演唱会 田馥甄"},
            {"tool": "bilibili", "query": "一一演唱会 田馥甄"},
            {"tool": "bilibili", "query": "田馥甄 红馆"},
            # To My Love 慶功音樂會（2011，台大体育馆，有 DVD/数字发行）
            {"tool": "youtube", "query": "田馥甄 To My Love 音乐会"},
            {"tool": "bilibili", "query": "田馥甄 To My Love 慶功 演唱会"},
            # IF+ 如果田馥甄巡迴演唱會Plus（2017 DVD，台北小巨蛋 2016/12 场次）
            {"tool": "youtube", "query": "田馥甄 IF+ 如果演唱会plus live"},
            {"tool": "bilibili", "query": "田馥甄 如果演唱会plus 台北"},
            # 演唱会的日常（2017 数字发行 live album，《日常》专辑10首现场版）
            {"tool": "youtube", "query": "田馥甄 演唱会的日常"},
            {"tool": "bilibili", "query": "田馥甄 演唱会的日常"},
            # 田调 Live in Life 野地小巡演（2025）
            {"tool": "youtube", "query": "田馥甄 田调 Live in Life 巡演 2025"},
            {"tool": "bilibili", "query": "田馥甄 田调 野地小巡演"},
            {"tool": "google", "query": "田馥甄 演唱会 全场 site:bilibili.com"},
            {"tool": "google", "query": "如果演唱会 田馥甄 site:bilibili.com"},
            # Love! To Hebe 音乐会（2010/10，华山文创园区 Legacy Taipei，首场个人演唱会）
            {"tool": "youtube", "query": "田馥甄 Love To Hebe 音乐会 Legacy 台北 2010"},
            {"tool": "bilibili", "query": "田馥甄 To Hebe 音乐会 Legacy 2010"},
            # 一一巡迴演唱會 各具体场次（泛搜索之外的细分）
            {"tool": "youtube", "query": "田馥甄 一一演唱会 台北 2020 小巨蛋"},
            {"tool": "youtube", "query": "田馥甄 一一演唱会 高雄 2022"},
            {"tool": "youtube", "query": "田馥甄 一一演唱会 台北 最终场 2023"},
            {"tool": "bilibili", "query": "田馥甄 一一演唱会 台北 2020"},
            {"tool": "bilibili", "query": "田馥甄 一一演唱会 高雄 2022"},
            {"tool": "bilibili", "query": "田馥甄 一一演唱会 2023 台北最终场"},
            # 如果演唱会 具体场次（高雄/香港红馆）
            {"tool": "youtube", "query": "田馥甄 如果演唱会 高雄巨蛋 2015"},
            {"tool": "youtube", "query": "田馥甄 如果演唱会 香港 红馆 2016"},
            # 渺小 纪录影音（2014 DVD，含8首MV + 影音装置展精华）
            {"tool": "youtube", "query": "田馥甄 渺小 纪录影音 DVD 2014"},
            {"tool": "bilibili", "query": "田馥甄 渺小 纪录 DVD"},
            # 如果巡迴演唱會 遗漏场次（台北首站2014/Plus高雄最终场2017）
            {"tool": "youtube", "query": "田馥甄 如果演唱会 台北 小巨蛋 2014 首站"},
            {"tool": "youtube", "query": "田馥甄 如果演唱会plus 高雄 最终场 2017"},
            {"tool": "bilibili", "query": "田馥甄 如果演唱会plus 高雄 2017"},
            # 田调 Live in Life 各具体场地（维基确认5处场地共10场）
            {"tool": "youtube", "query": "田馥甄 田调 台南 盐田 2025"},
            {"tool": "youtube", "query": "田馥甄 田调 高雄 卫武营 2025"},
            {"tool": "youtube", "query": "田馥甄 田调 屏东 恒春 2025"},
            {"tool": "youtube", "query": "田馥甄 田调 南投 埔里 暨南大学 2025"},
            {"tool": "bilibili", "query": "田馥甄 田调 台南 盐田"},
            {"tool": "bilibili", "query": "田馥甄 田调 高雄 卫武营"},
            {"tool": "bilibili", "query": "田馥甄 田调 屏东 恒春 砖窑"},
            # 小夜曲音乐舞台剧（2016-2017，田馥甄×莎妹劇團，共22场）
            {"tool": "youtube", "query": "田馥甄 小夜曲 莎妹 音乐剧"},
            {"tool": "bilibili", "query": "田馥甄 小夜曲 莎妹"},
            # 渺小 专辑微巡演
            {"tool": "youtube", "query": "田馥甄 渺小 微巡听歌会"},
            {"tool": "bilibili", "query": "田馥甄 渺小 微巡听歌会"},
            # 如果巡迴演唱會 遗漏大陆/海外场次（共38场23城，目前仅搜台北/高雄/香港）
            {"tool": "youtube", "query": "田馥甄 如果演唱会 上海 2015"},
            {"tool": "youtube", "query": "田馥甄 如果演唱会 北京 2016"},
            {"tool": "youtube", "query": "田馥甄 如果演唱会 新加坡 Singapore 2016"},
            {"tool": "bilibili", "query": "田馥甄 如果演唱会 上海"},
            {"tool": "bilibili", "query": "田馥甄 如果演唱会 北京"},
            # 田调 高雄卫武营 SHE合体（2025/6/21-22，Ella+Selina空降助阵，网络确认）
            {"tool": "youtube", "query": "SHE 田馥甄 田调 高雄 卫武营 2025 合体"},
            {"tool": "bilibili", "query": "SHE 合体 田馥甄 卫武营 2025"},
            # SHE 历代演唱会影像（从 file 7 移入，统一归并至演唱会文件）
            {"tool": "youtube", "query": "SHE Together Forever concert"},
            {"tool": "youtube", "query": "SHE 演唱会"},
            {"tool": "youtube", "query": "SHE 奇幻乐园 台北演唱会"},
            {"tool": "youtube", "query": "SHE 移动城堡演唱会 红磡"},
            {"tool": "youtube", "query": "SHE 爱而为一 世界巡迴演唱会"},
            {"tool": "youtube", "query": "SHE 2gether4ever ENCORE 演唱会"},
            {"tool": "bilibili", "query": "SHE 田馥甄 演唱会"},
            {"tool": "bilibili", "query": "SHE 移动城堡演唱会"},
            {"tool": "bilibili", "query": "SHE 爱而为一演唱会"},
            {"tool": "youtube", "query": "SHE 2gether4ever Together Forever 世界巡演 2013"},
            {"tool": "bilibili", "query": "SHE Together Forever 2gether4ever 演唱会 2013"},
            {"tool": "youtube", "query": "SHE 十七音乐会 2018 两厅院艺文广场"},
            {"tool": "bilibili", "query": "SHE 十七音乐会 2018"},
        ],
    },
    # ------------------------------------------------------------------
    # File 5: 综艺节目视频
    # ------------------------------------------------------------------
    {
        "file_id": 5,
        "output_path": "节目与访谈/综艺节目.md",
        "title": "田馥甄综艺节目视频",
        "description": "按节目分组：梦想的声音（逐期）、其他综艺、历史片段。每条注明原唱。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 梦想的声音 演员"},
            {"tool": "youtube", "query": "Hebe 梦想的声音"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 黑色柳丁"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 凡人歌"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 Play我呸"},
            {"tool": "youtube", "query": "田馥甄 综艺"},
            {"tool": "youtube", "query": "SHE 康熙来了"},
            {"tool": "youtube", "query": "田馥甄 节目"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 痒"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 无与伦比的美丽"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 当你"},
            {"tool": "youtube", "query": "田馥甄 梦想的声音 追梦人"},
            {"tool": "youtube", "query": "Hebe 梦想的声音 full 合集"},
            {"tool": "bilibili", "query": "梦想的声音 田馥甄", "page": 1},
            {"tool": "bilibili", "query": "梦想的声音 田馥甄", "page": 2},
            # 演员（薛之谦）明确搜索（YouTube 破千万，与节目名"演员"易混淆）
            {"tool": "youtube", "query": "田馥甄 梦想的声音 演员 薛之谦"},
            # 梦想的声音颠峰歌会（收官特别节目，含"当你"/"追梦人"，B站独立收录）
            {"tool": "youtube", "query": "梦想的声音 颠峰歌会 田馥甄"},
            {"tool": "bilibili", "query": "梦想的声音 颠峰歌会 田馥甄"},
            # 其他综艺
            {"tool": "youtube", "query": "田馥甄 天天向上"},
            {"tool": "bilibili", "query": "田馥甄 综艺"},
            {"tool": "bilibili", "query": "田馥甄 梦想的声音 合集"},
            # 补充：田馥甄个人综艺出演（非 SHE 团体）
            {"tool": "youtube", "query": "田馥甄 康熙来了"},
            {"tool": "youtube", "query": "田馥甄 快乐大本营"},
            {"tool": "bilibili", "query": "田馥甄 快乐大本营"},
            {"tool": "youtube", "query": "田馥甄 非常静距离"},
            # 金曲奖现场表演（第25届2014/第31届2020/第32届2021 均有独立演出）
            {"tool": "youtube", "query": "田馥甄 金曲奖 表演 颁奖典礼"},
            {"tool": "bilibili", "query": "田馥甄 金曲奖 表演"},
            # 台湾综艺
            {"tool": "youtube", "query": "田馥甄 娱乐百分百"},
            {"tool": "bilibili", "query": "田馥甄 综艺 2023"},
            # 跨年晚会演出
            {"tool": "youtube", "query": "田馥甄 跨年 演唱 表演"},
            {"tool": "bilibili", "query": "田馥甄 跨年 跨年晚会"},
            # KKBOX 风云榜（2010年度最佳新人等）
            {"tool": "youtube", "query": "田馥甄 KKBOX 风云榜 表演"},
            {"tool": "bilibili", "query": "田馥甄 KKBOX 风云榜"},
            # 330音乐田（2010，The Wall 慈善生日音乐会，个人发片前热身）
            {"tool": "youtube", "query": "田馥甄 330音乐田 The Wall 2010"},
            {"tool": "bilibili", "query": "田馥甄 330音乐田 2010"},
            # 金曲奖逐届表演（第31届2020受邀表演/第32届2021获三项大奖）
            {"tool": "youtube", "query": "田馥甄 金曲奖 第31届 2020 表演"},
            {"tool": "youtube", "query": "田馥甄 金曲奖 第32届 2021 得奖 表演"},
            {"tool": "bilibili", "query": "田馥甄 金曲奖 2021 得奖"},
            # 小夜曲音乐舞台剧（可归类为综艺/特别演出）
            {"tool": "bilibili", "query": "田馥甄 小夜曲 音乐剧 莎妹"},
            # 大陆访谈节目
            {"tool": "youtube", "query": "田馥甄 鲁豫有约"},
            {"tool": "bilibili", "query": "田馥甄 鲁豫有约"},
            # Hito流行音乐奖表演（多次获Hito最佳女歌手）
            {"tool": "youtube", "query": "田馥甄 Hito流行音乐奖 表演"},
            # 梦想的声音 遗漏神曲
            {"tool": "youtube", "query": "田馥甄 梦想的声音 要死就一定要死在你手里"},
            {"tool": "bilibili", "query": "田馥甄 梦想的声音 要死就一定要死在你手里"},
            # 我想和你唱 第三季（2018，湖南卫视，田馥甄确认出演，与韩红合唱《魔鬼中的天使》）— 完全遗漏
            {"tool": "youtube", "query": "田馥甄 我想和你唱 第三季 2018"},
            {"tool": "youtube", "query": "田馥甄 韩红 魔鬼中的天使 我想和你唱"},
            {"tool": "bilibili", "query": "田馥甄 我想和你唱 2018 湖南卫视"},
            {"tool": "bilibili", "query": "田馥甄 我想和你唱 小幸运 重新编曲"},
        ],
    },
    # ------------------------------------------------------------------
    # File 6: 采访视频
    # ------------------------------------------------------------------
    {
        "file_id": 6,
        "output_path": "节目与访谈/采访访谈.md",
        "title": "田馥甄采访与访谈视频",
        "description": "专访、采访、金曲奖访谈等。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 采访"},
            {"tool": "youtube", "query": "Hebe Tien interview"},
            {"tool": "youtube", "query": "田馥甄 专访 2020"},
            {"tool": "youtube", "query": "田馥甄 专访 2021"},
            {"tool": "youtube", "query": "田馥甄 无人知晓 专访"},
            {"tool": "youtube", "query": "田馥甄 金曲奖 采访"},
            {"tool": "youtube", "query": "Hebe 田馥甄 访谈"},
            {"tool": "bilibili", "query": "田馥甄 采访"},
            {"tool": "bilibili", "query": "田馥甄 专访"},
            {"tool": "bilibili", "query": "田馥甄 金曲奖 专访"},
            # 缺失年份专访
            {"tool": "youtube", "query": "田馥甄 专访 2016"},
            {"tool": "youtube", "query": "田馥甄 专访 2019"},
            {"tool": "youtube", "query": "田馥甄 专访 2023"},
            {"tool": "bilibili", "query": "田馥甄 专访 2016"},
            {"tool": "bilibili", "query": "田馥甄 专访 2019"},
            {"tool": "bilibili", "query": "田馥甄 一一演唱会 专访"},
            {"tool": "google", "query": "Hebe Tien interview 2021 2022"},
            {"tool": "google", "query": "田馥甄 深度专访"},
            # 补充：所有遗漏年份专访（专辑/演唱会发行节点）
            {"tool": "youtube", "query": "田馥甄 专访 2010 To Hebe"},
            {"tool": "youtube", "query": "田馥甄 专访 2011 My Love"},
            {"tool": "youtube", "query": "田馥甄 专访 2013 渺小"},
            {"tool": "youtube", "query": "田馥甄 专访 2014 如果演唱会"},
            {"tool": "youtube", "query": "田馥甄 专访 2015 小幸运"},
            {"tool": "youtube", "query": "田馥甄 专访 2017 日常 IF+"},
            {"tool": "youtube", "query": "田馥甄 专访 2018 自己的房间"},
            {"tool": "youtube", "query": "田馥甄 专访 2022 一周的朋友"},
            {"tool": "youtube", "query": "田馥甄 专访 2025 田调 巡演"},
            {"tool": "bilibili", "query": "田馥甄 专访 2020 无人知晓"},
            {"tool": "bilibili", "query": "田馥甄 专访 2022"},
            {"tool": "bilibili", "query": "田馥甄 专访 2025"},
            {"tool": "google", "query": "田馥甄 深度专访 2020 2021 site:bilibili.com"},
            # 2024年专访（一一最终场与田调之间的空白年份）
            {"tool": "youtube", "query": "田馥甄 专访 2024"},
            {"tool": "bilibili", "query": "田馥甄 专访 2024"},
            # 第32届金曲奖得奖专访（2021，获最佳华语女歌手等三项大奖）
            {"tool": "youtube", "query": "田馥甄 金曲奖 2021 最佳华语女歌手 得奖 专访"},
            {"tool": "bilibili", "query": "田馥甄 金曲奖 2021 最佳女歌手 专访"},
            # 重点深度访谈
            {"tool": "youtube", "query": "田馥甄 理科太太 采访"},
            {"tool": "youtube", "query": "田馥甄 唐绮阳 访谈"},
            {"tool": "bilibili", "query": "田馥甄 理科太太"},
            # 第六张专辑 2024 试听会相关采访（2024/9/2 正式举办，多媒体确认）
            {"tool": "youtube", "query": "田馥甄 第六张专辑 试听 2024"},
            {"tool": "bilibili", "query": "田馥甄 第六张专辑 2024 试听"},
        ],
    },
    # ------------------------------------------------------------------
    # File 7: SHE MV与演出
    # ------------------------------------------------------------------
    {
        "file_id": 7,
        "output_path": "MV/SHE_MV.md",
        "title": "S.H.E MV 完整列表",
        "description": "S.H.E MV 按年代排列，注明 Hebe 在各曲中的作用（领唱/主唱/合唱）。",
        "searches": [
            {"tool": "youtube", "query": "S.H.E MV official"},
            {"tool": "youtube", "query": "SHE Super Star MV"},
            {"tool": "youtube", "query": "SHE 不想长大 MV"},
            {"tool": "youtube", "query": "SHE SHERO MV"},
            {"tool": "youtube", "query": "SHE 美丽新世界 MV"},
            {"tool": "youtube", "query": "SHE 花又开好了 MV"},
            # 经典 MV 补充（女生宿舍/美丽新世界 时期）
            {"tool": "youtube", "query": "SHE 恋人未满 MV"},
            {"tool": "youtube", "query": "SHE 波斯猫 MV"},
            # 近年 SHE 单曲（15/17 周年）
            {"tool": "youtube", "query": "SHE 永远都在 MV"},
            {"tool": "youtube", "query": "SHE 十七 MV 吴青峰"},
            {"tool": "bilibili", "query": "SHE MV"},
            # 补充：遗漏的标志性 MV（按年代）
            {"tool": "youtube", "query": "SHE 下一站天后 MV"},
            {"tool": "bilibili", "query": "SHE 下一站天后 MV"},
            {"tool": "youtube", "query": "SHE 一眼万年 MV 天外飞仙"},
            {"tool": "youtube", "query": "SHE 怎么办 MV 花样少年少女"},
            {"tool": "youtube", "query": "SHE 花都开好了 MV 蔷薇之恋"},
            {"tool": "youtube", "query": "SHE 你快乐我随意 MV"},
            {"tool": "youtube", "query": "SHE 候鸟 MV 再见了可鲁"},
            {"tool": "youtube", "query": "SHE 你曾是少年 MV 少年班"},
            {"tool": "bilibili", "query": "SHE 一眼万年 天外飞仙"},
            # 补充：遗漏的高人气/标志性 MV（按专辑年代，维基确认均为正式发行曲目）
            {"tool": "youtube", "query": "SHE 热带雨林 MV"},
            {"tool": "youtube", "query": "SHE 中国话 MV"},
            {"tool": "youtube", "query": "SHE 天灰 MV"},
            {"tool": "youtube", "query": "SHE 半糖主义 MV"},
            {"tool": "youtube", "query": "SHE 我爱你 MV"},
            {"tool": "youtube", "query": "SHE 触电 MV"},
            {"tool": "youtube", "query": "SHE 他还是不懂 MV"},
            {"tool": "youtube", "query": "SHE 沿海公路的出口 MV"},
            {"tool": "youtube", "query": "SHE Ring Ring Ring MV"},
            {"tool": "youtube", "query": "SHE 殊途 MV 仙剑云之凡"},
            {"tool": "youtube", "query": "SHE 星光 MV 真命天女"},
            {"tool": "youtube", "query": "SHE 痛快 MV"},
            {"tool": "bilibili", "query": "SHE 热带雨林 MV"},
            {"tool": "bilibili", "query": "SHE 中国话 MV"},
            # 高人气名曲 MV 补充
            {"tool": "youtube", "query": "SHE Remember MV"},
            {"tool": "youtube", "query": "SHE 爱呢 MV"},
            {"tool": "youtube", "query": "SHE 听袁惟仁弹吉他 MV"},
            {"tool": "youtube", "query": "SHE 宇宙小姐 MV"},
            {"tool": "youtube", "query": "SHE 心还是热的 MV"},
            # 遗漏经典单曲 MV
            {"tool": "youtube", "query": "SHE 完美Kasanova MV"},
            {"tool": "bilibili", "query": "SHE 完美Kasanova MV"},
            {"tool": "youtube", "query": "SHE 说你爱我 MV"},
            {"tool": "bilibili", "query": "SHE 说你爱我 MV"},
        ],
    },
    # ------------------------------------------------------------------
    # File 8: 合唱与合作
    # ------------------------------------------------------------------
    {
        "file_id": 8,
        "output_path": "歌曲与合作/合唱合作.md",
        "title": "田馥甄合唱与合作",
        "description": "与其他歌手的合唱、合作视频。",
        "searches": [
            {"tool": "youtube", "query": "田馥甄 林宥嘉 给小孩"},
            {"tool": "youtube", "query": "田馥甄 吴青峰"},
            {"tool": "youtube", "query": "田馥甄 魏如萱"},
            {"tool": "youtube", "query": "田馥甄 五月天"},
            {"tool": "youtube", "query": "田馥甄 合唱"},
            # 飞轮海 × Hebe（2006，东方朱丽叶 OST，维基确认）
            {"tool": "youtube", "query": "飞轮海 只对你有感觉 Hebe 田馥甄"},
            {"tool": "bilibili", "query": "飞轮海 只对你有感觉 田馥甄"},
            # 陈珊妮 × Hebe（2008，陈珊妮专辑《如果有一件事是重要的》）
            {"tool": "youtube", "query": "陈珊妮 离别曲 田馥甄"},
            {"tool": "bilibili", "query": "陈珊妮 离别曲 田馥甄"},
            # 阿信 × Hebe（2019，五月天 Life Live 专辑，爱情的模样）
            {"tool": "youtube", "query": "阿信 田馥甄 爱情的模样"},
            {"tool": "bilibili", "query": "阿信 田馥甄 爱情的模样"},
            # 手牵手 2021（第32届金曲奖最佳华语女歌手入围者联合演唱抗疫曲）
            {"tool": "youtube", "query": "手牵手 2021 田馥甄 金曲奖"},
            {"tool": "bilibili", "query": "手牵手 2021 田馥甄 金曲奖"},
            # 洪敬尧 × Hebe（2010，电影《阿爸》OST，老唱盘）
            {"tool": "youtube", "query": "田馥甄 洪敬尧 老唱盘"},
            {"tool": "bilibili", "query": "田馥甄 合唱"},
            {"tool": "bilibili", "query": "田馥甄 合作"},
            # 吴青峰 × SHE × Hebe（2018，SHE 17周年纪念曲《十七》，吴青峰词曲）
            {"tool": "youtube", "query": "吴青峰 SHE 十七 田馥甄"},
            {"tool": "bilibili", "query": "吴青峰 SHE 十七 田馥甄"},
            # Ella × Hebe（《公主Selina》，送给受伤 Selina 的生日歌，Ella 词曲，两人合唱）
            {"tool": "youtube", "query": "Ella Hebe 公主Selina"},
            {"tool": "bilibili", "query": "Ella Hebe 公主Selina"},
            # 许光汉 × 田馥甄（一一演唱会 2023/8/12 合唱《一日》）
            {"tool": "youtube", "query": "田馥甄 许光汉 一日"},
            # 安溥（张悬）× 田馥甄（一一演唱会 2023/8/6 合唱〈如何〉〈最好的时光〉）
            {"tool": "youtube", "query": "安溥 张悬 田馥甄 一一演唱会 合唱"},
            {"tool": "bilibili", "query": "安溥 田馥甄 合唱"},
            # SHE 合体 × 一一演唱会（2023/8/11，Selina+Ella 担任嘉宾，合唱〈给小孩〉〈美丽新世界〉）
            {"tool": "youtube", "query": "田馥甄 SHE 一一演唱会 2023 合体 美丽新世界 给小孩"},
            {"tool": "bilibili", "query": "田馥甄 SHE 一一演唱会 合体"},
            # 吴青峰 × 田馥甄（一一演唱会 2023/8/13 最终场，合唱〈你在烦恼什么〉〈讽刺的情书〉〈妳〉〈十七〉）
            {"tool": "youtube", "query": "吴青峰 田馥甄 一一演唱会 你在烦恼什么"},
            {"tool": "bilibili", "query": "吴青峰 田馥甄 一一演唱会 合唱"},
            # 林宥嘉 × 田馥甄（如果演唱会 2015/9/19 高雄场，合唱〈寂寞寂寞就好〉〈傻子〉）
            {"tool": "youtube", "query": "田馥甄 林宥嘉 如果演唱会 高雄 合唱"},
            # 蔡依林 Ugly Beauty 演唱会嘉宾神仙合唱
            {"tool": "youtube", "query": "蔡依林 田馥甄 刻在我心底的名字 Ugly Beauty 演唱会"},
            {"tool": "bilibili", "query": "蔡依林 田馥甄 刻在我心底的名字"},
            # 苏运莹 × 田馥甄 《野子》（2015年度盛典，KKBOX/Spotify 有收录）— 完全遗漏
            {"tool": "youtube", "query": "田馥甄 苏运莹 野子 合唱"},
            {"tool": "bilibili", "query": "田馥甄 苏运莹 野子"},
            # 徐佳莹 × 田馥甄 《双声道》— 完全遗漏
            {"tool": "youtube", "query": "田馥甄 徐佳莹 双声道"},
            {"tool": "bilibili", "query": "田馥甄 徐佳莹 双声道"},
            # 韩红 × 田馥甄 《魔鬼中的天使》（2018《我想和你唱》现场，人民网确认）— 完全遗漏
            {"tool": "youtube", "query": "田馥甄 韩红 魔鬼中的天使"},
            {"tool": "bilibili", "query": "田馥甄 韩红 魔鬼中的天使"},
            # 魏如萱 × 田馥甄（一一演唱会 2023 台北嘉宾，补充具体场次语境）
            {"tool": "youtube", "query": "田馥甄 魏如萱 一一演唱会 合唱"},
        ],
    },
]
