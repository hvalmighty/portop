export interface User {
  username: string;
  full_name: string;
  email: string;
  role: string;
  entities: string[];
  permissions: string[];
}

export interface Entity {
  code: string;
  name: string;
  reporting_ccy: string;
}

export interface AccountSummary {
  account_id: number;
  code: string;
  name: string;
  entity: string;
  base_ccy: string;
  mandate: string;
  model_id: number | null;
  aum: number;
  nav: number;
  cash: number;
  gross: number;
  net: number;
  pnl: number;
  day_pnl: number;
  gross_vs_aum_pct: number;
  largest_symbol: string | null;
  largest_pct: number;
  share: Record<string, number>;
  positions: number;
}

export interface PositionRow {
  position_id: number;
  account: string;
  symbol: string;
  name: string;
  asset_class: string;
  inst_type: string;
  ccy: string;
  issuer: string;
  sector: string;
  rating: string | null;
  qty: number;
  avg_px: number;
  mark: number;
  exposure: number;
  exposure_rep: number;
  market_value_rep: number;
  mtm_pnl_rep: number;
  day_pnl_rep: number;
  pnl_pct: number;
  weight_pct: number;
  maturity: string | null;
  duration: number | null;
}

export interface Overview {
  reporting_ccy: string;
  totals: { positions: number; gross: number; net: number; mtm_pnl: number; day_pnl: number; aum: number; nav: number };
  accounts: AccountSummary[];
  positions: PositionRow[];
}

export interface RuleResult {
  rule_id: number;
  code: string;
  name: string;
  severity: string;
  passed: boolean;
  observed: number;
  limit: number;
  subject: string;
  message: string;
}

export interface Compliance {
  status: "PASS" | "WARN" | "FAIL";
  checked_at?: string;
  results: RuleResult[];
}

export interface Order {
  id: number;
  account: string;
  symbol: string;
  name: string;
  asset_class: string;
  ccy: string;
  side: "BUY" | "SELL";
  qty: number;
  limit_px: number | null;
  mark: number;
  status: string;
  source: string;
  batch_id: string | null;
  compliance_status: string | null;
  compliance: Compliance;
  override_reason: string | null;
  est_cost: number;
  created_by: string;
  approved_by: string | null;
  reject_reason: string | null;
  fill_px: number | null;
  notional: number;
  created_at: string;
}

export interface Instrument {
  id: number;
  symbol: string;
  name: string;
  asset_class: string;
  type: string;
  ccy: string;
  issuer: string;
  sector: string;
  country: string;
  rating: string | null;
  coupon: number | null;
  maturity: string | null;
  duration: number | null;
  price: number;
  prev_close: number;
  chg_pct: number;
  esg_score: number | null;
  is_active: boolean;
}

export interface Breach {
  id: number;
  rule: string;
  rule_name: string;
  category: string;
  severity: string;
  account: string;
  kind: string;
  subject: string;
  observed: number;
  limit: number;
  message: string;
  status: string;
  detected_at: string;
  resolved_at: string | null;
  notes: { ts: string; user: string; text: string; status?: string }[];
  age_hours: number;
}

export interface Tick {
  symbol: string;
  price: number;
  chg_pct: number;
  ccy: string;
  asset_class: string;
}
