# app/game_core/gnubg_parser.py
import re
from typing import Optional, List

_MOVE_ISLAND_RE = re.compile(
    r"((?:"
    r"\b(?:bar|off|\d{1,2})\*?"
    r"(?:/(?:bar|off|\d{1,2})\*?)+"
    r"(?:\(\d+\))?"
    r"\s*"
    r")+)",
    re.IGNORECASE,
)

def extract_move_island(line: str) -> Optional[str]:
    if "Eq.:" not in line:
        return None
    left = line.rsplit("Eq.:", 1)[0].rstrip()
    m = _MOVE_ISLAND_RE.search(left)
    if m:
        return m.group(1).strip()
    return None

def _expand_chain_token(token: str) -> list[str]:
    token = token.strip()
    if not token:
        return []
    cnt = 1
    m = re.search(r"\((\d+)\)\s*$", token)
    if m:
        cnt = int(m.group(1))
        token = token[:m.start()].strip()
    
    parts_raw = token.split('/')
    if len(parts_raw) <= 2:
        return [token] * cnt
    
    nodes: list[tuple[str, bool]] = []
    for p in parts_raw:
        p = p.strip()
        has_star = p.endswith('*')
        if has_star:
            p = p[:-1]
        nodes.append((p, has_star))
    
    segs: list[str] = []
    for i in range(len(nodes) - 1):
        fr, _ = nodes[i]
        to, star_on_to = nodes[i + 1]
        segs.append(f"{fr}/{to}{'*' if star_on_to else ''}")
    
    original_segs = list(segs) 
    
    # Повторяем *всю* оригинальную цепочку (cnt - 1) раз
    if cnt > 1 and original_segs:
        for _ in range(cnt - 1):
            segs.extend(original_segs)
            
    return segs

def _parse_gnubg_segments(move_text: str) -> list[str]:
    if not move_text:
        return []
    s = move_text.strip()
    tokens = [t for t in s.split() if "/" in t]
    moves: list[str] = []
    for tok in tokens:
        moves.extend(_expand_chain_token(tok))
    return moves

def parse_gnubg_to_atomic_moves(move_string: str, bot_sign: int, dice: list) -> list[dict]:
    
    final_atomic_moves_gnubg = []
    simple_move_segments = _parse_gnubg_segments(move_string)
    
    for segment in simple_move_segments:
        match = re.match(r"(\w+)/(\w+)\*?", segment.strip())
        if not match:
            continue
            
        _from, _to = match.groups()

        try:
            _from_int = 25 if _from.lower() == 'bar' else int(_from)
            _to_int = 0 if _to.lower() == 'off' else int(_to)
        except ValueError:
            continue

        final_atomic_moves_gnubg.append({'from': _from_int, 'to': _to_int})

    converted_moves = []
    if bot_sign == -1:
        for move in final_atomic_moves_gnubg:
            new_from = 0
            if move['from'] == 25: new_from = 27
            elif 1 <= move['from'] <= 24: new_from = 25 - move['from']
            else: new_from = move['from']
            
            new_to = 0
            if move['to'] == 0: new_to = 26
            elif 1 <= move['to'] <= 24: new_to = 25 - move['to']
            else: new_to = move['to']
            
            converted_moves.append({'from': new_from, 'to': new_to})
        return converted_moves
    else:
        for move in final_atomic_moves_gnubg:
            new_from = move['from']
            new_to = move['to']
            if new_from == 25: new_from = 25
            if new_to == 0: new_to = 0
            converted_moves.append({'from': new_from, 'to': new_to})
        return converted_moves