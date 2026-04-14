def parse_rank(card_str):
    """解析单张牌的点数"""
    rank_str = card_str.split(" ")[0].upper()
    if rank_str in ["K", "Q", "J", "10", "KING", "QUEEN", "JACK"]:
        return 0
    elif rank_str in ["A", "ACE"]:
        return 1
    else:
        try:
            return int(rank_str)
        except:
            return None

def update_shoe_stats(oc, rank_counts, game_stats):
    """更新剩余牌统计"""
    game_stats[oc.winner] += 1
    all_cards = oc.player_cards + oc.banker_cards
    for card in all_cards:
        val = parse_rank(card)
        if val is not None and rank_counts[val] > 0:
            rank_counts[val] -= 1
    return rank_counts, game_stats