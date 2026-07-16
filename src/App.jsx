import { useEffect, useState, useRef } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

const PRODUCTS = {
  petrol: { label: "Petrol", color: "var(--petrol)" },
  hsd: { label: "Diesel", color: "var(--diesel)" },
  sko: { label: "Kerosene", color: "var(--kerosene)" },
  ldo: { label: "Light diesel", color: "var(--ldo)" },
  jp1: { label: "Jet A-1", color: "var(--jp1)" },
};
const RANGES = [
  { k: "1Y", years: 1 },
  { k: "5Y", years: 5 },
  { k: "10Y", years: 10 },
  { k: "All", years: null },
];

const rs = (n) =>
  "₨" +
  Number(n).toLocaleString("en-PK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const rsPlain = (n) =>
  Number(n).toLocaleString("en-PK", { maximumFractionDigits: 0 });
const longDate = (t) =>
  new Date(t).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

const prefersReduced =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function useCountUp(target, ms = 900) {
  const [v, setV] = useState(prefersReduced ? target : 0);
  const started = useRef(false);
  useEffect(() => {
    if (target == null) return;
    if (prefersReduced) {
      setV(target);
      return;
    }
    if (started.current) {
      setV(target);
      return;
    }
    started.current = true;
    let start;
    const ease = (p) => 1 - Math.pow(1 - p, 3);
    const step = (ts) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / ms, 1);
      setV(target * ease(p));
      if (p < 1) requestAnimationFrame(step);
    };
    const id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [target, ms]);
  return v;
}

function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      <div className="tip__date">{longDate(label)}</div>
      {payload.map((e) => (
        <div className="tip__row" key={e.dataKey}>
          <span>{PRODUCTS[e.dataKey]?.label ?? e.dataKey}</span>
          <span>{rs(e.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [active, setActive] = useState(["petrol", "hsd"]);
  const [range, setRange] = useState("All");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/prices.json`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(setData)
      .catch(() => setErr("Couldn't load the price data. Try refreshing."));
  }, []);

  const latest = data?.revisions?.[data.revisions.length - 1];
  const prev = data?.revisions?.[data.revisions.length - 2];
  const petrolNow = latest?.products?.petrol ?? null;
  const animated = useCountUp(petrolNow);

  if (err)
    return (
      <div className="wrap">
        <p className="state">{err}</p>
      </div>
    );
  if (!data)
    return (
      <div className="wrap">
        <p className="state">Loading prices…</p>
      </div>
    );

  const change = latest?.change?.petrol ?? 0;
  const up = change > 0;

  const cutoff =
    range === "All"
      ? -Infinity
      : Date.parse(latest.effective_from) -
        RANGES.find((r) => r.k === range).years * 365.25 * 864e5;

  const chartData = data.revisions
    .map((r) => ({ t: Date.parse(r.effective_from), ...r.products }))
    .filter((d) => d.t >= cutoff);

  const toggle = (k) =>
    setActive((a) => (a.includes(k) ? a.filter((x) => x !== k) : [...a, k]));

  return (
    <div className="wrap">
      <div className="eyebrow">Pakistan · Notified petroleum prices</div>

      <section className="pump">
        <div className="pump__label">Petrol · per litre</div>
        <div className="pump__price">
          <small>₨</small>
          {animated.toLocaleString("en-PK", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </div>
        {change !== 0 && (
          <div className={`pump__delta ${up ? "up" : "down"}`}>
            {up ? "▲" : "▼"} {rs(Math.abs(change))} vs{" "}
            {prev ? longDate(Date.parse(prev.effective_from)) : "—"}
          </div>
        )}
        <div className="pump__meta">
          {["hsd", "sko", "ldo", "jp1"]
            .filter((k) => latest.products[k] != null)
            .map((k) => (
              <div className="pump__stat" key={k}>
                <span>{PRODUCTS[k].label}</span>
                <b>{rs(latest.products[k])}</b>
              </div>
            ))}
        </div>
        <div className="pump__foot">
          Effective {longDate(Date.parse(latest.effective_from))} ·{" "}
          {data.revision_count} revisions on record
        </div>
      </section>

      <div className="controls">
        <div className="group">
          <div className="group__label">Products</div>
          <div className="chips">
            {Object.entries(PRODUCTS).map(([k, p]) => (
              <button
                key={k}
                className="chip"
                aria-pressed={active.includes(k)}
                onClick={() => toggle(k)}
              >
                <span className="chip__dot" style={{ background: p.color }} />
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="group">
          <div className="group__label">Range</div>
          <div className="chips">
            {RANGES.map((r) => (
              <button
                key={r.k}
                className="chip"
                aria-pressed={range === r.k}
                onClick={() => setRange(r.k)}
              >
                {r.k}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="chart">
        <ResponsiveContainer width="100%" height={420}>
          <LineChart
            data={chartData}
            margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
          >
            <CartesianGrid stroke="#E0DCD0" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t) => new Date(t).getFullYear()}
              stroke="#B8B3A6"
              tick={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
            <YAxis
              tickFormatter={rsPlain}
              width={56}
              stroke="#B8B3A6"
              tick={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
            <Tooltip content={<Tip />} />
            {active.map((k) => (
              <Line
                key={k}
                type="stepAfter"
                dataKey={k}
                name={PRODUCTS[k].label}
                stroke={PRODUCTS[k].color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="foot">
        Source: Pakistan State Oil notified POL prices, scraped twice daily ·
        Prices exclude freight to retail outlet; pump price varies slightly by
        location ·{" "}
        <a href="https://github.com/Mohid2025/pak-fuel">
          Dataset & code on GitHub
        </a>
      </p>
    </div>
  );
}
