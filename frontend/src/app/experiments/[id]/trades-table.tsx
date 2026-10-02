"use client";

import { useState } from "react";
import { EmptyState } from "@/components/ui";
import { num, usd } from "@/lib/format";
import type { Trade } from "@/lib/schemas";

const PAGE = 25;

export function TradesTable({ trades }: { trades: Trade[] }) {
  const [page, setPage] = useState(0);
  if (trades.length === 0) {
    return <EmptyState title="No trades">The short average never crossed above the long average in this period.</EmptyState>;
  }
  const pages = Math.ceil(trades.length / PAGE);
  const shown = trades.slice(page * PAGE, page * PAGE + PAGE);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="table">
          <caption className="sr-only">Executed trades</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Signal (close)</th>
              <th scope="col">Filled (open)</th>
              <th scope="col">Side</th>
              <th scope="col" className="num">Open</th>
              <th scope="col" className="num">Fill price</th>
              <th scope="col" className="num">Shares</th>
              <th scope="col" className="num">Notional</th>
              <th scope="col" className="num">Fee</th>
              <th scope="col" className="num">Slippage</th>
              <th scope="col" className="num">Cash after</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((t) => (
              <tr key={t.seq}>
                <td>{t.seq}</td>
                <td>{t.signal_date}</td>
                <td>{t.trade_date}</td>
                <td className={t.side === "buy" ? "text-emerald-700" : "text-rose-700"}>{t.side}</td>
                <td className="num">{num(t.open_price, 4)}</td>
                <td className="num">{num(t.exec_price, 4)}</td>
                <td className="num">{num(t.shares, 4)}</td>
                <td className="num">{usd(t.notional)}</td>
                <td className="num">{usd(t.fee)}</td>
                <td className="num">{usd(t.slippage_cost)}</td>
                <td className="num">{usd(t.cash_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mt-3 flex items-center gap-3 text-sm">
          <button className="btn-secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page + 1} of {pages}</span>
          <button className="btn-secondary" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </>
  );
}
