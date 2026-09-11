from app.services.relevance import is_relevant_video, relevance_score


def test_accepts_tisora_style_product_content():
    caption = "法式一字肩花朵连衣裙，收腰显瘦，上身太有气质了 #穿搭"
    assert is_relevant_video(caption)
    assert relevance_score(caption) >= 60


def test_rejects_celebrity_red_carpet_content():
    caption = "白鹿身穿祖海高定礼裙亮相明星红毯 #时尚"
    assert not is_relevant_video(caption)
    assert relevance_score(caption) == 0


def test_rejects_wedding_and_hanfu_content():
    assert not is_relevant_video("新娘订婚宴敬酒服，新中式婚礼穿搭")
    assert not is_relevant_video("汉服走秀传统服饰明制婚服")


def test_rejects_celebrity_events_seen_in_production_results():
    assert not is_relevant_video("杨幂虎纹吊带抹胸短裙，野性辣妹气场直接炸场 #杨幂 #品牌活动")
    assert not is_relevant_video("孟娜黑色抹胸长裙搭配盘发造型 #抖音心动追剧盛典")
    assert not is_relevant_video("感谢ASA礼服 #世界小姐 #选美冠军")
    assert not is_relevant_video("这条伴娘裙生日约会都很适合的一条轻礼服")


def test_keeps_wedding_adjacent_dress_with_multiple_party_signals():
    caption = (
        "nico梅尼耶结婚的伴娘裙今晚六点见哦 "
        "生日约会漂亮饭都很适合的一条轻礼服 气质又有辨识度 "
        "随便一拍就很美#穿搭 #轻礼服 #梅尼耶结婚"
    )
    assert relevance_score(caption, search_keyword="生日约会连衣裙") >= 60
    assert is_relevant_video(caption, search_keyword="生日约会连衣裙")


def test_rejects_pure_bridesmaid_content_without_party_signals():
    assert not is_relevant_video("今年流行的伴娘礼服，结婚当天统一穿")


def test_rejects_entertainment_and_fan_accounts_by_author():
    caption = "黑色吊带纱裙造型，这气质太美啦"
    assert not is_relevant_video(caption, author_name="OG娱乐")
    assert not is_relevant_video(caption, author_name="小U梨追星")


def test_keeps_product_focused_tisora_inspiration():
    caption = "一字肩褶皱收腰长袖连衣裙，弹力面料，高腰大摆版型，显瘦遮肉"
    assert is_relevant_video(caption, author_name="钟意好物")


def test_requires_a_commercial_product_term():
    assert not is_relevant_video("今天分享高级感穿搭，真的很好看")


def test_accepts_broader_commercial_dress_terms():
    assert is_relevant_video("今天试穿一条很显瘦的女装连衣裙")
    assert is_relevant_video("小众女装连衣裙分享，约会穿搭推荐")


def test_keyword_exact_match_improves_score():
    caption = "小众设计感连衣裙女，上身显瘦"
    base = relevance_score(caption)
    matched = relevance_score(caption, search_keyword="小众设计感连衣裙女")
    assert matched > base
