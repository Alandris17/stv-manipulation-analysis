from __future__ import annotations
from fractions import Fraction
import sys
import time
from typing import List, Dict, Tuple, Set
import argparse

# Configuration
DEBUG = False  # set to True to receive the [DEBUG] prints


# Parsing the .toi file (with truncation + indifferences)
def split_top_level_commas(s: str) -> List[str]:
    """
    Split a string on commas that are at 'top level', i.e. not inside {...}.
    Example: "3,4,5,{1,10},2" -> ["3", "4", "5", "{1,10}", "2"]
    """
    parts = []
    current = []
    depth = 0
    for ch in s:
        if ch == '{':
            depth += 1
            current.append(ch)
        elif ch == '}':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            part = ''.join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
    part = ''.join(current).strip()
    if part:
        parts.append(part)
    return parts


def parse_toi_with_ties(path: str) -> Tuple[List[str], List[Tuple[int, List[List[str]]]], Dict[str, str]]:
    """
    Parse a PrefLib .toi file.

    Returns:
        candidates: list of candidate IDs as strings ("1","2",...)
        ballots:    list of (count, rank_blocks), where rank_blocks is
                    a list of lists of candidate IDs.
                    Example: [[3],[8],[5,7]] means 3 > 8 > {5,7}.
        cand_names: dict mapping candidate ID (string) -> human-readable name
                    parsed from header lines "# ALTERNATIVE NAME k: ...".
    """
    ballots: List[Tuple[int, List[List[str]]]] = []
    cand_set: Set[str] = set()
    cand_names: Dict[str, str] = {}

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')

            # Header: pull candidate names
            if line.startswith('# ALTERNATIVE NAME'):
                # example: "# ALTERNATIVE NAME 1: Jackie Kasabach"
                # we grab the number and the name after colon
                try:
                    prefix, name_part = line.split(':', 1)
                    name = name_part.strip()
                    # prefix like "# ALTERNATIVE NAME 1"
                    parts = prefix.split()
                    cand_id = parts[-1]  # "1"
                    cand_names[cand_id] = name
                except Exception:
                    pass
                continue

            # Other comments or empty lines – skip for ballots
            if not line.strip() or line.lstrip().startswith('#'):
                continue

            # Ballot lines: "count: ranking"
            if ':' not in line:
                continue
            left, right = line.split(':', 1)
            count_str = left.strip()
            if not count_str.isdigit():
                continue
            count = int(count_str)
            ranking_raw = right.strip()
            if not ranking_raw:
                continue

            items = split_top_level_commas(ranking_raw)
            rank_blocks: List[List[str]] = []

            for item in items:
                item = item.strip()
                if not item:
                    continue
                if item.startswith('{') and item.endswith('}'):
                    # Tie block
                    inner = item[1:-1]
                    tied_ids = [tok.strip() for tok in inner.split(',') if tok.strip()]
                    if tied_ids:
                        rank_blocks.append(tied_ids)
                        for cid in tied_ids:
                            cand_set.add(cid)
                else:
                    # Single candidate
                    cid = item
                    rank_blocks.append([cid])
                    cand_set.add(cid)

            ballots.append((count, rank_blocks))

    # Candidate IDs sorted numerically
    candidates = sorted(cand_set, key=lambda x: int(x))

    # If some names are missing in header, fill with generic labels
    for cid in candidates:
        if cid not in cand_names:
            cand_names[cid] = f"Candidate {cid}"

    return candidates, ballots, cand_names


# Rule-13 STV
def stv_rule13(candidates: List[str],
               ballots: List[Tuple[int, List[List[str]]]]
               ) -> Tuple[Set[str], List[Set[str]]]:
    """
    Rule 13 STV with parallel elimination of all lowest plurality candidates.

    candidates: list of candidate IDs (strings)
    ballots:    list of (weight, rank_blocks), rank_blocks as [[c1],[c2],...] or ties.

    Returns:
        winners: set of candidate IDs eliminated last
        layers:  list of sets; each is candidates eliminated in that round
    """
    remaining: Set[str] = set(candidates)
    elimination_layers: List[Set[str]] = []

    while remaining:
        scores = {c: Fraction(0, 1) for c in remaining}

        for weight, rank_blocks in ballots:
            # find first block intersecting remaining
            chosen_block = None
            for block in rank_blocks:
                block_rem = [c for c in block if c in remaining]
                if block_rem:
                    chosen_block = block_rem
                    break
            if chosen_block is None:
                # exhausted ballot
                continue

            share = Fraction(weight, len(chosen_block))
            for c in chosen_block:
                scores[c] += share

        # In pathological cases, some candidate might never get any votes
        # Make sure all have an entry (already in init)
        min_score = min(scores[c] for c in remaining)
        losers = {c for c in remaining if scores[c] == min_score}

        elimination_layers.append(losers)
        remaining -= losers

    winners = elimination_layers[-1]
    return winners, elimination_layers


# Helpers for manipulation: preferences over sets, strategic ballots, etc.
def linear_extension(rank_blocks: List[List[str]]) -> List[str]:
    """
    Break ties deterministically: sort each tied block by candidate ID,
    and concatenate.
    """
    ext: List[str] = []
    for block in rank_blocks:
        ext.extend(sorted(block, key=lambda x: int(x)))
    return ext


def better_outcome_for_voter(rank_blocks: List[List[str]],
                             W_new: Set[str],
                             W_old: Set[str]) -> bool:
    """
    Returns True if W_new is STRICTLY better than W_old for a voter
    with the given rank_blocks (Optimistic assumption).
    Strictly better means the voter's favorite candidate in W_new
    is ranked in a strictly higher block than their favorite in W_old.
    """
    if W_new == W_old:
        return False
        
    # Find index of the best block containing a candidate from W_new
    idx_new = float('inf')
    for i, block in enumerate(rank_blocks):
        if not set(block).isdisjoint(W_new):
            idx_new = i
            break
            
    # Find index of the best block containing a candidate from W_old
    idx_old = float('inf')
    for i, block in enumerate(rank_blocks):
        if not set(block).isdisjoint(W_old):
            idx_old = i
            break
            
    # Lower index means better rank. 
    # New outcome is strictly better if we find a winner earlier in the ranking 
    # than we did in the old outcome.
    return idx_new < idx_old


def compute_first_round_plurality(candidates: List[str],
                                  ballots: List[Tuple[int, List[List[str]]]]
                                  ) -> Dict[str, Fraction]:
    """
    Compute first-round plurality scores under STV interpretation (ties split).
    """
    scores = {c: Fraction(0, 1) for c in candidates}
    for weight, rank_blocks in ballots:
        for block in rank_blocks:
            if block:
                share = Fraction(weight, len(block))
                for c in block:
                    scores[c] += share
                break
    return scores


def generate_strategic_ballots(candidates: List[str],
                               ballots: List[Tuple[int, List[List[str]]]],
                               c: str,
                               W_truth: Set[str],
                               max_opponents: int = 4
                               ) -> List[List[List[str]]]:
    """
    Generate a small set of plausible strategic ballots that all put
    candidate c on top.

    Heuristics:
      - default ballot: c at top, then main opponents in decreasing
        first-round score, then others.
      - anti-winners ballot: c at top, then strong non-winners, then
        truthful winners last.
    """
    scores = compute_first_round_plurality(candidates, ballots)

    opp_sorted = [x for x in sorted(candidates,
                                    key=lambda x: (-scores[x], int(x)))
                  if x != c]

    # Default: c > (strongest opponents) > (rest)
    top_opps = opp_sorted[:max_opponents]
    rest = [x for x in opp_sorted if x not in top_opps]
    default_order = [c] + top_opps + rest
    default_ballot = [[x] for x in default_order]

    strategic = []
    strategic.append(default_ballot)

    # Anti-winners: c > strong non-winners > winners
    non_winners = [x for x in opp_sorted if x not in W_truth]
    anti_order = [c] + non_winners + [w for w in candidates if w in W_truth and w != c]
    anti_ballot = [[x] for x in anti_order]
    strategic.append(anti_ballot)

    # Deduplicate
    unique = []
    seen = set()
    for rb in strategic:
        key = tuple(tuple(block) for block in rb)
        if key not in seen:
            seen.add(key)
            unique.append(rb)
    return unique


# Coalitional manipulation search
def find_smallest_manipulation(candidates: List[str],
                               ballots: List[Tuple[int, List[List[str]]]],
                               cand_names: Dict[str, str],
                               W_truth: Set[str],
                               K_max: int = 100):
    """
    GREEDY Search: Checks ALL losing candidates to find the absolute 
    smallest coalition size k.
    """
    # Pre-calculate elimination order for sorting
    # We want to check the "strongest" losers (last eliminated) first.
    _, elim_layers = stv_rule13(candidates, ballots)
    
    # Flatten layers in reverse order (Winner -> Runner-up -> ... -> First Loser)
    sorted_candidates = []
    for layer in reversed(elim_layers):
        # Sort within layer by ID for determinism, though usually layer size is 1
        sorted_candidates.extend(sorted(layer, key=lambda x: int(x)))
    
    # Prepare ballot types
    ballot_types = []
    for (w, rb) in ballots:
        ballot_types.append({
            'weight': w,
            'rank_blocks': rb,
            'ext_order': linear_extension(rb)
        })

    best_manipulation = None
    
    # Iterate through candidates in "Strongest First" order
    for c in sorted_candidates:
        if c in W_truth: 
            continue

        # Optimization: If we already found a coalition of size k=X,
        # we don't need to check coalitions >= X for other candidates.
        current_limit = K_max
        if best_manipulation is not None:
            current_limit = best_manipulation['k']

        # Find eligible voters for candidate c
        elig_indices = []
        for idx, bt in enumerate(ballot_types):
            ext = bt['ext_order']
            if c not in ext: continue
            
            # Eligible if c is strictly better than current winners
            # (Using the heuristic check logic we defined)
            rb = bt['rank_blocks']
            if better_outcome_for_voter(rb, {c}, W_truth): # Check against singleton {c} as proxy
                 elig_indices.append(idx)

        if not elig_indices: continue

        # Greedy Heuristic: Sort eligible types by weight (largest blocks first)
        elig_indices.sort(key=lambda i: (
            ballot_types[i]['ext_order'].index(c), 
            ballot_types[i]['weight']
        ), reverse=True)
        
        total_elig_weight = sum(ballot_types[i]['weight'] for i in elig_indices)
        
        # Generate Strategic Ballots
        strategic_ballots = generate_strategic_ballots(candidates, ballots, c, W_truth)

        # Search for k
        # We only search up to current_limit (strictly less if we want to beat it)
        for k in range(1, current_limit):
            if total_elig_weight < k: break

            if DEBUG and k % 10 == 0:
                print(f"[DEBUG] Checking k={k} for {cand_names[c]}...")

            # Construct Greedy Coalition
            current_x = {}
            needed = k
            for idx in elig_indices:
                available = ballot_types[idx]['weight']
                take = min(needed, available)
                current_x[idx] = take
                needed -= take
                if needed == 0: break
            
            # Construct Base Profile (Remove coalition votes)
            base_ballots = []
            for j, bt in enumerate(ballot_types):
                take = current_x.get(j, 0)
                new_w = bt['weight'] - take
                if new_w > 0:
                    base_ballots.append((new_w, bt['rank_blocks']))

            # Test each strategic ballot
            for s in strategic_ballots:
                test_ballots = list(base_ballots)
                test_ballots.append((k, s))

                W_new, _ = stv_rule13(candidates, test_ballots)

                # Verification: Do these voters actually prefer W_new?
                ok_all = True
                for j_idx, taken in current_x.items():
                    if taken <= 0: continue
                    rb = ballot_types[j_idx]['rank_blocks']
                    if not better_outcome_for_voter(rb, W_new, W_truth):
                        ok_all = False
                        break
                
                if ok_all:
                    print(f"[FOUND] Better manipulation for {cand_names[c]} at k={k}!")
                    best_manipulation = {
                        'k': k,
                        'target': c,
                        'target_name': cand_names[c],
                        'coalition_types': current_x,
                        'strategic_ballot': s,
                        'W_new': W_new
                    }
                    # We found a k for this candidate. 
                    # Since we search k=1..limit, this is the optimal k for THIS candidate.
                    # We can stop checking this candidate and move to the next 
                    # (with a stricter limit).
                    break 
            
            # If we found a manipulation for this candidate, break the k-loop
            if best_manipulation is not None and best_manipulation['target'] == c:
                break

    return best_manipulation


# Main
def main():
    parser = argparse.ArgumentParser(
        description="Analyze coalitional manipulation in Rule-13 STV elections using PrefLib .toi files."
    )

    parser.add_argument(
        "file",
        help="Path to the PrefLib .toi election file."
    )

    parser.add_argument(
        "--kmax",
        type=int,
        default=10000,
        help="Maximum coalition size to search. Default: 10000."
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug messages during the manipulation search."
    )

    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    path = args.file
    print(f"Reading election from: {path}")

    candidates, ballots, cand_names = parse_toi_with_ties(path)
    print(f"Parsed {len(candidates)} candidates and {len(ballots)} unique ballot types.")

    # Compute truthful STV outcome
    t0 = time.time()
    W_truth, elim_layers = stv_rule13(candidates, ballots)
    t1 = time.time()

    print("\n=== Truthful STV (Rule-13) result ===")
    print("Winner IDs:", sorted(W_truth, key=lambda x: int(x)))
    print("Winner names:", [cand_names[c] for c in sorted(W_truth, key=lambda x: int(x))])
    print(f"STV runtime: {t1 - t0:.4f} seconds")

    print("\nElimination layers (from first eliminated to last):")
    for r, layer in enumerate(elim_layers, start=1):
        print(
            f"  Round {r}: " +
            ", ".join(
                f"{c} ({cand_names[c]})"
                for c in sorted(layer, key=lambda x: int(x))
            )
        )

    print("\n=== Searching for coalitional manipulation ===")
    t2 = time.time()
    best = find_smallest_manipulation(
        candidates,
        ballots,
        cand_names,
        W_truth,
        K_max=args.kmax
    )
    t3 = time.time()

    print(f"\nManipulation search runtime: {t3 - t2:.4f} seconds "
          f"(K_max={args.kmax})")

    if best is None:
        print("No manipulation found within the given search bounds.")
    else:
        print("\n=== Manipulation found ===")
        print(f"Target candidate: {best['target']} ({best['target_name']})")
        print(f"Smallest coalition size found: {best['k']}")

        print("\nCoalition composition:")
        for idx, cnt in best['coalition_types'].items():
            print(f"  Ballot type {idx}: {cnt} voter(s)")

        print("\nStrategic ballot they all submit:")
        for block in best['strategic_ballot']:
            if len(block) == 1:
                cid = block[0]
                print(f"  {cid} ({cand_names.get(cid, cid)})")
            else:
                names = ", ".join(
                    f"{cid} ({cand_names.get(cid, cid)})"
                    for cid in block
                )
                print(f"  {{{names}}}")

        print("\nNew winners if coalition manipulates:")
        for cid in sorted(best['W_new'], key=lambda x: int(x)):
            print(f"  {cid} ({cand_names[cid]})")


if __name__ == "__main__":
    main()
