"""Deterministic FIFO allocation of immutable broker executions in original currency."""
from collections import defaultdict
from decimal import Decimal

EPS = Decimal("0.000000001")


def number(value):
    return Decimal(str(value or 0))


def allocate_trades(rows):
    lots = defaultdict(list)
    groups = {}
    events = []
    for row in sorted(rows, key=lambda r: (r["timestamp"], r.get("order", 0), r["id"])):
        if row.get("asset_class") not in {"STOCK", "FUND"} or not row.get("ticker"):
            continue
        key = (row["isin"], row["currency"])
        kind = row["type"]
        quantity = abs(number(row["shares"]))
        if kind not in {"buy", "sell"}:
            if kind in {"split", "transfer_in", "transfer_out", "sell_cancelled", "delisted", "expiration", "warrant_exercise", "insolvency_proceedings"}:
                # Do not manufacture cost basis for corporate actions or missing transfers.
                for lot in lots[key]:
                    lot["known"] = False
                if kind in {"transfer_in", "sell_cancelled"}:
                    lots[key].append({"row": row, "remaining": quantity, "cost": Decimal(0), "known": False})
                elif kind == "split":
                    old = sum(lot["remaining"] for lot in lots[key])
                    if old:
                        for lot in lots[key]:
                            lot["remaining"] *= quantity / old
                else:
                    remaining = quantity
                    for lot in lots[key]:
                        consumed = min(lot["remaining"], remaining)
                        lot["remaining"] -= consumed
                        remaining -= consumed
                lots[key] = [lot for lot in lots[key] if lot["remaining"] > EPS]
                # Preserve the final cycle balance even when its last event is a transfer.
                for prior in reversed(events):
                    if prior["group"] == groups.get(key):
                        prior["remaining"] = float(sum(lot["remaining"] for lot in lots[key]))
                        break
            continue
        if quantity <= EPS:
            continue
        if not lots[key]:
            groups[key] = row["id"]
        group = groups.setdefault(key, row["id"])
        fees = abs(number(row.get("fees"))) + abs(number(row.get("tax")))
        event = {**row, "group": group, "allocations": [], "pnl": None, "pnl_pct": None,
                 "unallocated": 0.0, "remaining": 0.0}
        if kind == "buy":
            total_cost = quantity * number(row["price"]) + fees
            lots[key].append({"row": row, "remaining": quantity, "cost": total_cost / quantity,
                              "known": number(row["price"]) > 0})
        else:
            remaining = quantity
            basis = Decimal(0)
            known = number(row["price"]) > 0
            for lot in lots[key]:
                consumed = min(lot["remaining"], remaining)
                if consumed <= EPS:
                    continue
                cost = consumed * lot["cost"]
                proceeds = consumed * number(row["price"]) - fees * consumed / quantity
                event["allocations"].append({"buy_transaction_id": lot["row"]["id"],
                    "shares": float(consumed), "cost_basis": float(cost) if lot["known"] else None,
                    "net_proceeds": float(proceeds), "pnl": float(proceeds - cost) if lot["known"] else None,
                    "buy_date": lot["row"]["date"]})
                basis += cost
                known = known and lot["known"]
                remaining -= consumed
                lot["remaining"] -= consumed
                if remaining <= EPS:
                    break
            event["unallocated"] = float(max(Decimal(0), remaining))
            if remaining <= EPS and known and basis > 0:
                pnl = quantity * number(row["price"]) - fees - basis
                event.update(pnl=float(pnl), pnl_pct=float(pnl / basis * 100))
            lots[key] = [lot for lot in lots[key] if lot["remaining"] > EPS]
        event["remaining"] = float(sum(lot["remaining"] for lot in lots[key]))
        events.append(event)
    return events
