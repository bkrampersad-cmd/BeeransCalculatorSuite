import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import json, os, sys
import json, os, sys
import json, os, sys
import numpy_financial as npf
import math
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

APP_VERSION = "1.0.0"   # displayed in the About window

# ── Palette ───────────────────────────────────────────────
NAV_BG   = "#1F3864"
NAV_ACT  = "#2F5496"
NAV_HOV  = "#16294E"
CARD     = "#FFFFFF"
APP_BG   = "#EEF2F7"
ACCENT   = "#1565C0"
INPUT_BG = "#EBF3FB"
RES_BG   = "#D6E4F0"
TEXT     = "#1A202C"
MUTED    = "#718096"
ALT_ROW  = "#F7FAFC"
INPUT_BORDER  = "#B8CCE4"   # input border
BTN_SECONDARY = "#E2E8F0"   # secondary / clear button bg
DIAGRAM_DIM   = "#1F3864"   # diagram lines (theme-aware)

INPUT_BORDER  = "#B8CCE4"   # input border
BTN_SECONDARY = "#E2E8F0"   # secondary / clear button bg
DIAGRAM_DIM   = "#1F3864"   # diagram lines (theme-aware)

BORDER   = "#CBD5E0"
SUCCESS  = "#276749"
ERROR_C  = "#C53030"
HDR_TBL  = "#1F3864"

F_H1  = ("Segoe UI", 18, "bold")
F_H2  = ("Segoe UI", 12, "bold")
F_LBL = ("Segoe UI", 10)
F_INP = ("Segoe UI", 10)
F_RES = ("Segoe UI", 11, "bold")
F_BTN = ("Segoe UI", 10, "bold")
F_NAV = ("Segoe UI", 10, "bold")
F_SM  = ("Segoe UI", 10)
F_TBL = ("Segoe UI", 10)


# ─────────────────────────────────────────────────────────
# CALCULATION HELPERS
# ─────────────────────────────────────────────────────────

def calc_rate(nper, pmt, pv, comp=12):
    """Annual interest rate from periodic rate * comp periods."""
    try:
        r = npf.rate(nper, -abs(pmt), abs(pv), 0)
        return float(r) * comp
    except Exception:
        return None

def calc_pmt(annual_rate, nper, pv, comp=12):
    """Monthly payment."""
    try:
        return float(-npf.pmt(annual_rate / comp, nper, abs(pv), 0))
    except Exception:
        return None

def cumipmt(rate_per_period, nper, pv):
    total = sum(float(npf.ipmt(rate_per_period, p, nper, pv, 0)) for p in range(1, nper + 1))
    return total

def cumprinc(rate_per_period, nper, pv):
    total = sum(float(npf.ppmt(rate_per_period, p, nper, pv, 0)) for p in range(1, nper + 1))
    return total

def sln(cost, salvage, life):
    return (cost - salvage) / life

def syd(cost, salvage, life, period):
    return (cost - salvage) * (life - period + 1) / (life * (life + 1) / 2)

def ddb(cost, salvage, life, period, factor=2):
    """Double (or variable factor) declining balance for one period."""
    rate = factor / life
    book = cost
    for _ in range(period - 1):
        d = min(book * rate, max(book - salvage, 0))
        book -= d
    return min(book * rate, max(book - salvage, 0))

def basic_depreciation_schedule(cost, salvage, life, method, factor=2):
    rows = []
    cumul = 0.0
    for yr in range(1, life + 1):
        if method == "SL":
            d = sln(cost, salvage, life)
        elif method == "SYOD":
            d = syd(cost, salvage, life, yr)
        else:  # DB
            d = ddb(cost, salvage, life, yr, factor)
        d = min(d, cost - salvage - cumul)
        d = max(d, 0)
        cumul += d
        rows.append((yr, d, cumul, cost - cumul))
    return rows

def macrs_first_year_fraction(convention, placed):
    """placed = quarter (1-4) for Mid-Quarter, month (1-12) for Mid-Month."""
    if convention == "Half-Year":
        return 0.5
    elif convention == "Mid-Quarter":
        Q = int(placed)
        return 1 - (Q - 0.5) / 4
    elif convention == "Mid-Month":
        M = int(placed)
        return (12.5 - M) / 12
    return 0.5

def macrs_last_year(n, convention, placed):
    if convention == "Half-Year":
        return math.ceil(n + 0.5)
    elif convention == "Mid-Quarter":
        Q = int(placed)
        return math.ceil(n + Q / 4)
    elif convention == "Mid-Month":
        M = int(placed)
        return math.ceil(n + (M - 0.5) / 12)
    return math.ceil(n + 0.5)

def macrs_schedule(basis, n, method, factor, convention, placed):
    f1   = macrs_first_year_fraction(convention, placed)
    last = macrs_last_year(n, convention, placed)
    db_rate = factor / n

    rows = []
    remaining = basis
    cumul = 0.0

    for yr in range(1, last + 1):
        if remaining <= 1e-6:
            break

        if method == "SL":
            # SL with convention fraction
            if yr == 1:
                d = basis / n * f1
            elif yr == last:
                d = remaining
            else:
                # remaining life in full years
                elapsed = yr - 1 - (1 - f1)
                rem_life = n - elapsed
                d = remaining / rem_life if rem_life > 0 else remaining
        else:  # DB-SL
            if yr == 1:
                d = round(remaining * db_rate * f1, 2)
            elif yr == last:
                d = remaining
            else:
                # remaining recovery period for SL comparison
                if convention == "Half-Year":
                    rem_rec = last - yr + 0.5
                else:
                    rem_rec = last - yr + f1
                db_d  = round(remaining * db_rate, 2)
                sl_d  = round(remaining / rem_rec, 2) if rem_rec > 0 else remaining
                d = max(db_d, sl_d)

        d = min(max(d, 0), remaining)
        cumul += d
        remaining = basis - cumul
        rows.append({
            "year": yr,
            "depreciation": d,
            "cumulative":   cumul,
            "book_value":   max(remaining, 0),
            "rate":         d / basis if basis else 0,
        })

    return rows

def macrs_full_schedule(basis, n, method, factor, convention, placed, adjustments):
    """MACRS with per-year basis adjustments (dict year->amount)."""
    f1   = macrs_first_year_fraction(convention, placed)
    last = macrs_last_year(n, convention, placed)
    db_rate = factor / n

    rows = []
    book = basis
    cumul = 0.0

    for yr in range(1, last + 1):
        adj = adjustments.get(yr, 0.0)
        current_basis = book + adj

        if current_basis <= 1e-6:
            rows.append({"year": yr, "adjustment": adj, "basis": 0,
                         "dj_sl": 0, "dj_db": 0,
                         "depreciation": 0, "cumulative": cumul, "book_value": 0})
            book = 0
            continue

        if method == "SL":
            dj_sl = current_basis / n * f1 if yr == 1 else (
                    current_basis if yr == last else current_basis / max(last - yr + 0.5, 0.5))
            dj_db = 0
            d = dj_sl
        else:
            if yr == 1:
                dj_db = round(current_basis * db_rate * f1, 2)
                dj_sl = round(current_basis / n * f1, 2)
            elif yr == last:
                dj_db = current_basis
                dj_sl = current_basis
            else:
                rem_rec = last - yr + 0.5 if convention == "Half-Year" else last - yr + f1
                dj_db = round(current_basis * db_rate, 2)
                dj_sl = round(current_basis / rem_rec, 2) if rem_rec > 0 else current_basis
            d = max(dj_sl, dj_db)

        d = min(max(d, 0), current_basis)
        cumul += d
        book = current_basis - d

        rows.append({"year": yr, "adjustment": adj, "basis": current_basis,
                     "dj_sl": dj_sl if method != "SL" else 0,
                     "dj_db": dj_db if method != "SL" else 0,
                     "depreciation": d, "cumulative": cumul, "book_value": max(book, 0)})

    return rows

def amortization_schedule(loan, annual_rate, years, ppy, extra_pmt=0, start_date=None):
    """Full amortization schedule."""
    rate_per = annual_rate / ppy
    nper = years * ppy
    if rate_per == 0:
        base_pmt = loan / nper
    else:
        base_pmt = float(-npf.pmt(rate_per, nper, loan))

    rows = []
    balance = loan
    current_date = start_date or date.today()
    months_per_period = 12 / ppy

    for p in range(1, nper + 1):
        if balance <= 0.005:
            break
        interest = balance * rate_per
        principal = min(base_pmt - interest + extra_pmt, balance)
        total_pmt = interest + principal
        balance -= principal
        balance = max(balance, 0)
        rows.append({
            "period":    p,
            "date":      current_date.strftime("%b %Y"),
            "payment":   round(total_pmt, 2),
            "extra":     round(extra_pmt, 2),
            "interest":  round(interest, 2),
            "principal": round(principal, 2),
            "balance":   round(balance, 2),
        })
        try:
            current_date += relativedelta(months=int(months_per_period))
        except Exception:
            pass

    return base_pmt, rows

def inches_to_ruler(val):
    whole = int(val)
    frac  = val - whole
    sixteenth = round(frac * 16)
    if sixteenth == 0:
        return f'{whole}"'
    elif sixteenth == 16:
        return f'{whole + 1}"'
    else:
        g = math.gcd(sixteenth, 16)
        n, d = sixteenth // g, 16 // g
        return f'{whole} {n}/{d}"' if whole else f'{n}/{d}"'

def inches_to_feet(val):
    feet  = int(val // 12)
    rem   = val - feet * 12
    ruler = inches_to_ruler(rem)
    return f"{feet}' {ruler}"


# ─────────────────────────────────────────────────────────
# REUSABLE UI COMPONENTS
# ─────────────────────────────────────────────────────────

def make_card(parent, **kwargs):
    f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10,
                     border_width=1, border_color=BORDER, **kwargs)
    return f

def section_header(parent, title):
    f = ctk.CTkFrame(parent, fg_color=NAV_BG, corner_radius=8, height=38)
    f.pack(fill="x", pady=(0, 10))
    f.pack_propagate(False)
    ctk.CTkLabel(f, text=title, font=ctk.CTkFont("Segoe UI", 11, "bold"),
                 text_color="white", anchor="w").pack(side="left", padx=14, pady=0)
    return f

def labeled_entry(parent, label, default="", width=160, on_enter=None, fs=10):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=3)
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", fs),
                 text_color=TEXT, width=220, anchor="w").pack(side="left")
    var = tk.StringVar(value=str(default))
    ent = ctk.CTkEntry(row, textvariable=var, width=width,
                       fg_color=INPUT_BG, border_color=INPUT_BORDER,
                       font=ctk.CTkFont("Segoe UI", fs))
    ent.pack(side="left", padx=(8, 0))
    if on_enter:
        ent.bind("<Return>", lambda e: on_enter())
    return var

def labeled_entry_var(parent, label_var, default="", width=160, on_enter=None, fs=10):
    """Like labeled_entry but accepts a StringVar for the label so it can update dynamically."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=3)
    ctk.CTkLabel(row, textvariable=label_var, font=ctk.CTkFont("Segoe UI", fs),
                 text_color=TEXT, width=220, anchor="w").pack(side="left")
    var = tk.StringVar(value=str(default))
    ent = ctk.CTkEntry(row, textvariable=var, width=width,
                       fg_color=INPUT_BG, border_color=INPUT_BORDER,
                       font=ctk.CTkFont("Segoe UI", fs))
    ent.pack(side="left", padx=(8, 0))
    if on_enter:
        ent.bind("<Return>", lambda e: on_enter())
    return var

def labeled_option(parent, label, choices, default=None, width=160, fs=10, command=None):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=3)
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", fs),
                 text_color=TEXT, width=220, anchor="w").pack(side="left")
    var = tk.StringVar(value=default or choices[0])
    opt = ctk.CTkOptionMenu(row, variable=var, values=choices, width=width,
                            fg_color=INPUT_BG, button_color=ACCENT,
                            text_color=TEXT, dropdown_text_color=TEXT,
                            font=ctk.CTkFont("Segoe UI", fs),
                            command=command)
    opt.pack(side="left", padx=(8, 0))
    return var

def result_row(parent, label, var_ref, fmt=None, color=TEXT, lbl_fs=10, val_fs=11, row_h=34):
    row = ctk.CTkFrame(parent, fg_color=RES_BG, corner_radius=6, height=row_h)
    row.pack(fill="x", pady=2)
    row.pack_propagate(False)
    ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", lbl_fs),
                 text_color=MUTED, width=220, anchor="w").pack(side="left", padx=10)
    lbl = ctk.CTkLabel(row, textvariable=var_ref,
                       font=ctk.CTkFont("Segoe UI", val_fs, "bold"),
                       text_color=color)
    lbl.pack(side="left", padx=8)
    return lbl

def calc_button(parent, text, command, clear_cmd=None, sample_cmd=None):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(anchor="w", pady=(10, 4), padx=20)
    if sample_cmd:
        ctk.CTkButton(row, text="Sample", command=sample_cmd,
                      fg_color=INPUT_BG, text_color=ACCENT,
                      hover_color=RES_BG,
                      font=ctk.CTkFont("Segoe UI", 10), width=72, height=36,
                      corner_radius=8).pack(side="left", padx=(0, 6))
    if clear_cmd:
        ctk.CTkButton(row, text="Clear", command=clear_cmd,
                      fg_color=BTN_SECONDARY, text_color=TEXT,
                      hover_color=BORDER,
                      font=ctk.CTkFont("Segoe UI", 10), width=72, height=36,
                      corner_radius=8).pack(side="left", padx=(0, 6))
    btn = ctk.CTkButton(row, text=text, command=command,
                        fg_color=ACCENT, hover_color=NAV_ACT,
                        font=ctk.CTkFont("Segoe UI", 10, "bold"),
                        height=36, corner_radius=8)
    btn.pack(side="left")
    return btn

def fmt_currency(v):
    if v is None: return "—"
    return f"${abs(v):,.2f}"

def fmt_pct(v):
    if v is None: return "—"
    return f"{v * 100:.4f}%"

def fmt_num(v, decimals=2):
    if v is None: return "—"
    return f"{v:,.{decimals}f}"

def make_table(parent, columns, col_widths, height=200):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Suite.Treeview",
                    background=CARD, fieldbackground=CARD,
                    foreground=TEXT, font=("Segoe UI", 9),
                    rowheight=24, borderwidth=0)
    style.configure("Suite.Treeview.Heading",
                    background=HDR_TBL, foreground="white",
                    font=("Segoe UI", 9, "bold"), relief="flat")
    style.map("Suite.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
    style.map("Suite.Treeview.Heading", background=[("active", NAV_ACT)])

    frame = ctk.CTkFrame(parent, fg_color="transparent")

    tree = ttk.Treeview(frame, columns=columns, show="headings",
                        style="Suite.Treeview", height=height)
    for col, w in zip(columns, col_widths):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor="e", minwidth=40)
    tree.column(columns[0], anchor="c")

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)

    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    tree.tag_configure("alt", background=ALT_ROW)

    return frame, tree



# ─────────────────────────────────────────────────────────
# TAB 1 — BASIC CALCULATOR
# ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────
# KEYBOARD MIXIN — binds Enter to _calculate when tab active
# ─────────────────────────────────────────────────────────

class CalcTabMixin:
    """Adds activate/deactivate so Enter triggers _calculate."""
    def activate(self):
        self.winfo_toplevel().bind("<Return>", self._on_enter)

    def deactivate(self):
        try:
            self.winfo_toplevel().unbind("<Return>")
        except Exception:
            pass

    def _on_enter(self, event):
        # Skip if user is focused inside a text-entry widget
        if isinstance(event.widget, tk.Entry):
            return
        if hasattr(self, "_calculate"):
            self._calculate()



# ─────────────────────────────────────────────────────────
# SAFE MATH NAMESPACE for graphing eval()
# ─────────────────────────────────────────────────────────
SAFE_MATH_NS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "log": math.log10, "log10": math.log10, "ln": math.log,
    "log2": math.log2, "sqrt": math.sqrt, "abs": abs,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "__builtins__": {},
}

class BasicCalcTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._current  = "0"
        self._prev     = None
        self._op       = None
        self._new_num  = True
        self._mem_slots = [None]*8
        self._next_slot = 0
        self._mem_btns  = []
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Basic Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        body.columnconfigure(0, weight=1, uniform="half")
        body.columnconfigure(1, weight=1, uniform="half")
        body.rowconfigure(0, weight=1)

        # ── Left: calculator card ─────────────────────────────────────────
        calc_card = make_card(body)
        calc_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # ── Memory slot panel (left side of calc card) ────────────────────
        mem_panel = ctk.CTkFrame(calc_card, fg_color=INPUT_BG, corner_radius=8)
        mem_panel.pack(side="left", fill="y", padx=(10, 4), pady=10)
        ctk.CTkLabel(mem_panel, text="MEMORY",
                     font=ctk.CTkFont("Segoe UI", 7, "bold"),
                     text_color=MUTED).pack(pady=(8, 4))
        for i in range(8):
            btn = ctk.CTkButton(
                mem_panel, text=f"MR {i+1}\n—",
                command=lambda s=i: self._mr_slot(s),
                width=78, height=48,
                fg_color=CARD, hover_color=RES_BG,
                text_color=TEXT,
                font=ctk.CTkFont("Segoe UI", 9, "bold"),
                corner_radius=6)
            btn.pack(padx=6, pady=2)
            self._mem_btns.append(btn)
        tk.Frame(mem_panel, bg=INPUT_BG).pack(expand=True, fill="y")

        # ── Main calculator area (right side of calc card) ────────────────
        main_area = ctk.CTkFrame(calc_card, fg_color="transparent")
        main_area.pack(side="left", fill="both", expand=True)

        # Display
        disp = ctk.CTkFrame(main_area, fg_color=NAV_BG, corner_radius=8)
        disp.pack(fill="x", padx=(4, 14), pady=(14, 6))
        self._mem_var  = tk.StringVar(value="")
        self._expr_var = tk.StringVar(value="")
        self._disp_var = tk.StringVar(value="0")
        top_row = ctk.CTkFrame(disp, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(top_row, textvariable=self._mem_var,
                     font=ctk.CTkFont("Segoe UI", 9, "bold"),
                     text_color="#4FC3F7", anchor="w").pack(side="left")
        ctk.CTkLabel(top_row, textvariable=self._expr_var,
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color="#7A9CC8", anchor="e").pack(side="right")
        ctk.CTkLabel(disp, textvariable=self._disp_var,
                     font=ctk.CTkFont("Segoe UI", 30, "bold"),
                     text_color="white", anchor="e"
                     ).pack(fill="x", padx=12, pady=(2, 12))

        # Memory control row (MC, MS, M+, M− — MR removed; use left-side buttons)
        _mrow = ctk.CTkFrame(main_area, fg_color="transparent")
        _mrow.pack(anchor="center", pady=(2, 0))
        for lbl, cmd in [("MC", self._mc), ("M+", self._mplus)]:
            ctk.CTkButton(_mrow, text=lbl, command=cmd,
                          width=68, height=54, fg_color=INPUT_BG,
                          hover_color=INPUT_BORDER, text_color=TEXT,
                          font=ctk.CTkFont("Segoe UI", 11, "bold"),
                          corner_radius=6).pack(side="left", padx=2)

        # Main button grid
        ROWS = [
            [("%",   self._pct),  ("CE",  self._ce),    ("C",   self._clear), ("⌫",  self._back)],
            [("1/x", self._inv),  ("x²",  self._sq),    ("√x",  self._sqrt),  ("÷",  lambda: self._op_press("÷"))],
            [("7",   lambda: self._num("7")), ("8", lambda: self._num("8")), ("9", lambda: self._num("9")), ("×", lambda: self._op_press("×"))],
            [("4",   lambda: self._num("4")), ("5", lambda: self._num("5")), ("6", lambda: self._num("6")), ("−", lambda: self._op_press("−"))],
            [("1",   lambda: self._num("1")), ("2", lambda: self._num("2")), ("3", lambda: self._num("3")), ("+", lambda: self._op_press("+"))],
            [("+/-", self._sign), ("0",   lambda: self._num("0")),  (".",  self._dot), ("=",  self._equals)],
        ]
        grid = ctk.CTkFrame(main_area, fg_color="transparent")
        grid.pack(padx=(4, 14), pady=(6, 4))
        for r, row in enumerate(ROWS):
            for c, (lbl, cmd) in enumerate(row):
                is_op = lbl in ("÷", "×", "−", "+")
                is_eq = lbl == "="
                is_fn = lbl in ("%", "CE", "C", "⌫", "1/x", "x²", "√x", "+/-", ".")
                bg, fg, hov = (ACCENT,"white","#0D47A1") if is_eq else                               (NAV_ACT,"white",NAV_HOV) if is_op else                               ("#D6E4F0",NAV_BG,"#B8CCE4") if is_fn else                               ("#F0F4F8",TEXT,"#D6E4F0")
                ctk.CTkButton(grid, text=lbl, command=cmd,
                              width=68, height=54, fg_color=bg, hover_color=hov,
                              text_color=fg, font=ctk.CTkFont("Segoe UI", 13, "bold"),
                              corner_radius=6).grid(row=r, column=c, padx=3, pady=3)

        # Memory legend (updated)
        legend_data = [
            ("MC",     "Clear all 8 memory slots"),
            ("M+",     "Store in first available slot (wraps to MR 1 when all filled)"),
            ("MR 1-8", "Left side buttons — click any slot to recall its stored value"),
        ]
        legend = tk.Frame(main_area, bg=APP_BG)
        legend.pack(fill="x", padx=(4, 14), pady=(2, 14))
        for btn_lbl, desc in legend_data:
            row2 = tk.Frame(legend, bg=APP_BG)
            row2.pack(fill="x", padx=8)
            tk.Label(row2, text=btn_lbl, font=("Segoe UI", 9, "bold"),
                     fg=TEXT, bg=APP_BG, anchor="w", width=7).pack(side="left")
            tk.Label(row2, text=" — ", font=("Segoe UI", 9),
                     fg=MUTED, bg=APP_BG).pack(side="left")
            tk.Label(row2, text=desc, font=("Segoe UI", 9),
                     fg=MUTED, bg=APP_BG, anchor="w").pack(side="left")

        # ── Right: history ────────────────────────────────────────────────
        hist_card = make_card(body)
        hist_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        section_header(hist_card, "  HISTORY")
        self._hist_box = tk.Text(hist_card, font=("Segoe UI", 10), bg=CARD,
                                  fg=TEXT, relief="flat", state="disabled",
                                  wrap="word", highlightthickness=0, cursor="arrow")
        self._hist_box.pack(fill="both", expand=True, padx=14, pady=(4, 4))
        self._hist_box.tag_configure("expr",   foreground=MUTED,  font=("Segoe UI", 9))
        self._hist_box.tag_configure("result", foreground=ACCENT, font=("Segoe UI", 13, "bold"))
        self._hist_box.tag_configure("sep",    foreground=BORDER)
        ctk.CTkButton(hist_card, text="Clear History", command=self._clear_hist,
                      fg_color="transparent", hover_color=RES_BG,
                      text_color=MUTED, font=ctk.CTkFont("Segoe UI", 9),
                      height=26).pack(pady=(0, 10))

    # ── Calculator logic ──────────────────────────────────────
    def _fmt(self, val):
        if isinstance(val, float):
            if val != val: return "Error"          # NaN
            if abs(val) == float("inf"): return "Cannot divide by 0"
            if val == int(val) and abs(val) < 1e15:
                return str(int(val))
            return f"{val:.10g}"
        return str(val)

    def _set(self, val):
        self._current = self._fmt(val)
        self._disp_var.set(self._current)

    def _num(self, digit):
        if self._new_num:
            self._current = digit; self._new_num = False
        else:
            if self._current == "0" and digit != ".":
                self._current = digit
            elif len(self._current.lstrip("-").replace(".", "")) < 15:
                self._current += digit
        self._disp_var.set(self._current)

    def _dot(self):
        if self._new_num:
            self._current = "0."; self._new_num = False
        elif "." not in self._current:
            self._current += "."
        self._disp_var.set(self._current)

    def _compute(self, a, b, op):
        if op == "+": return a + b
        if op == "−": return a - b
        if op == "×": return a * b
        if op == "÷": return (a / b) if b != 0 else float("inf")
        return b

    def _op_press(self, op):
        val = float(self._current)
        if self._prev is not None and not self._new_num:
            val = self._compute(self._prev, val, self._op)
            self._set(val)
        self._prev = float(self._current) if self._new_num else val
        self._op = op; self._new_num = True
        self._expr_var.set(f"{self._fmt(self._prev)} {op}")

    def _equals(self):
        if self._prev is None or self._op is None: return
        a, b, op = self._prev, float(self._current), self._op
        try:
            result = self._compute(a, b, op)
        except Exception:
            self._disp_var.set("Error"); self._clear(); return
        expr_str = f"{self._fmt(a)} {op} {self._fmt(b)}"
        res_str  = self._fmt(result)
        self._add_history(expr_str, res_str)
        self._expr_var.set(f"{expr_str} =")
        self._set(result)
        self._prev = None; self._op = None; self._new_num = True

    def _clear(self):
        self._current = "0"; self._prev = None; self._op = None
        self._new_num = True; self._disp_var.set("0"); self._expr_var.set("")

    def _ce(self):
        self._current = "0"; self._new_num = True; self._disp_var.set("0")

    def _back(self):
        if self._new_num: return
        self._current = self._current[:-1] or "0"
        self._disp_var.set(self._current)

    def _sign(self):
        if self._current not in ("0", "Error"):
            self._current = self._current[1:] if self._current.startswith("-") else "-" + self._current
        self._disp_var.set(self._current)

    def _pct(self):
        try: self._set(float(self._current) / 100)
        except: pass

    def _inv(self):
        try: self._set(1 / float(self._current))
        except: pass

    def _sq(self):
        try: self._set(float(self._current) ** 2)
        except: pass

    def _sqrt(self):
        try: self._set(math.sqrt(float(self._current)))
        except: pass

    # ── Memory functions (4-slot system) ─────────────────────
    def _fmt_mem(self, val):
        """Format a value compactly for slot button display."""
        s = f"{val:.7g}"
        if "." in s: s = s.rstrip("0").rstrip(".")
        return s[:9] + "…" if len(s) > 9 else s

    def _mem_indicator(self):
        return "".join("■" if v is not None else "□" for v in self._mem_slots)

    def _mc(self):
        """Clear all 8 memory slots."""
        self._mem_slots = [None]*8
        self._next_slot = 0
        for i, b in enumerate(self._mem_btns):
            b.configure(text=f"MR {i+1}\n—", fg_color=CARD)
        self._mem_var.set("")

    def _mr(self):
        """Recall from last-filled slot (kept for keyboard compat)."""
        s = (self._next_slot - 1) % 8
        if self._mem_slots[s] is not None:
            self._set(self._mem_slots[s]); self._new_num = True

    def _mr_slot(self, slot):
        """Recall value from a specific slot."""
        if self._mem_slots[slot] is not None:
            self._set(self._mem_slots[slot]); self._new_num = True

    def _ms(self):
        """Overwrite the last-filled slot with current display value."""
        try:
            val = float(self._current)
            s = (self._next_slot - 1) % 8
            self._mem_slots[s] = val
            self._mem_btns[s].configure(
                text=f"MR {s+1}\n{self._fmt_mem(val)}", fg_color=RES_BG)
            self._mem_var.set(self._mem_indicator())
        except Exception: pass

    def _mplus(self):
        """Store in first empty slot; if all full, wrap to slot 0."""
        try:
            val = float(self._current)
            s = next((i for i in range(8) if self._mem_slots[i] is None), 0)
            self._mem_slots[s] = val
            self._mem_btns[s].configure(
                text=f"MR {s+1}\n{self._fmt_mem(val)}", fg_color=RES_BG)
            self._mem_var.set(self._mem_indicator())
            self._new_num = True
        except Exception: pass

    def _mminus(self):
        """Subtract display from the last-filled slot."""
        try:
            val = float(self._current)
            s = (self._next_slot - 1) % 8
            if self._mem_slots[s] is not None:
                self._mem_slots[s] -= val
                self._mem_btns[s].configure(
                    text=f"MR {s+1}\n{self._fmt_mem(self._mem_slots[s])}", fg_color=RES_BG)
                self._mem_var.set(self._mem_indicator())
            self._new_num = True
        except Exception: pass

    # ── Keyboard support ─────────────────────────────────────
    def activate(self):
        root = self.winfo_toplevel()
        root.bind("<Key>", self._on_key)

    def deactivate(self):
        try:
            self.winfo_toplevel().unbind("<Key>")
        except Exception:
            pass

    def _on_key(self, event):
        """Route keyboard input to calculator actions."""
        # Don't capture if an entry widget has focus on another tab
        if isinstance(event.widget, tk.Entry):
            return
        k = event.keysym
        c = event.char
        if c.isdigit() or k in (
                "KP_0","KP_1","KP_2","KP_3","KP_4",
                "KP_5","KP_6","KP_7","KP_8","KP_9"):
            self._num(c if c.isdigit() else k[-1])
        elif c == "." or k == "KP_Decimal":
            self._dot()
        elif c == "+" or k == "KP_Add":
            self._op_press("+")
        elif c == "-" or k in ("KP_Subtract", "minus"):
            self._op_press("−")
        elif c in ("*", "x") or k == "KP_Multiply":
            self._op_press("×")
        elif c == "/" or k == "KP_Divide":
            self._op_press("÷")
        elif c == "%":
            self._pct()
        elif k in ("Return", "KP_Enter", "equal"):
            self._equals()
        elif k == "BackSpace":
            self._back()
        elif k == "Escape":
            self._clear()
        elif k == "Delete":
            self._ce()

    def _add_history(self, expr, result):
        self._hist_box.configure(state="normal")
        self._hist_box.insert("1.0", "\n", "sep")
        self._hist_box.insert("1.0", f"  = {result}\n", "result")
        self._hist_box.insert("1.0", f"  {expr}\n", "expr")
        self._hist_box.configure(state="disabled")

    def _clear_hist(self):
        self._hist_box.configure(state="normal")
        self._hist_box.delete("1.0", "end")
        self._hist_box.configure(state="disabled")


# ─────────────────────────────────────────────────────────
# TAB 1 — LOAN CALCULATORS
# ─────────────────────────────────────────────────────────

class LoanCalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Loan Calculators",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)


        cols = ctk.CTkFrame(self, fg_color="transparent")
        cols.pack(fill="x", padx=20, pady=4)

        self._build_interest_rate(cols)
        self._build_monthly_payment(cols)
        self._build_percent_section()

    def _build_interest_rate(self, parent):
        card = make_card(parent)
        card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        section_header(card, "  CALCULATE INTEREST RATE")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.ir_loan    = labeled_entry(inner, "Loan Amount ($)",        "21303.60", on_enter=self._calc_interest_rate)
        self.ir_payment = labeled_entry(inner, "Monthly Payment ($)",    "674.88",  on_enter=self._calc_interest_rate)
        self.ir_periods = labeled_entry(inner, "Periods (months)",       "36",      on_enter=self._calc_interest_rate)
        self.ir_comp    = labeled_entry(inner, "Compounding Periods/yr", "12",      on_enter=self._calc_interest_rate)

        calc_button(inner, "Calculate →", self._calc_interest_rate, clear_cmd=self._clear_ir, sample_cmd=self._sample_ir)

        res = ctk.CTkFrame(card, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.ir_rate_v   = tk.StringVar(value="—")
        self.ir_int_v    = tk.StringVar(value="—")
        self.ir_princ_v  = tk.StringVar(value="—")
        self.ir_total_v  = tk.StringVar(value="—")
        result_row(res, "Annual Interest Rate",       self.ir_rate_v,  color=ACCENT)
        result_row(res, "Total Interest Amount",      self.ir_int_v)
        result_row(res, "Total Principal",            self.ir_princ_v)
        result_row(res, "Total Payment Amount",       self.ir_total_v)

    # ── Clear / Sample helpers ─────────────────────────────────
    @staticmethod
    def _set(vars_, val):
        for v in vars_: v.set(val)

    def _clear_ir(self):
        self._set([self.ir_loan,self.ir_payment,self.ir_periods,self.ir_comp],"")
        self._set([self.ir_rate_v,self.ir_int_v,self.ir_princ_v,self.ir_total_v],"—")
    def _sample_ir(self):
        self.ir_loan.set("21303.60"); self.ir_payment.set("674.88")
        self.ir_periods.set("36"); self.ir_comp.set("12")

    def _clear_mp(self):
        self._set([self.mp_loan,self.mp_rate,self.mp_per,self.mp_comp],"")
        self._set([self.mp_pmt_v,self.mp_int_v,self.mp_princ_v,self.mp_total_v],"—")
    def _sample_mp(self):
        self.mp_loan.set("21303.60"); self.mp_rate.set("8.741")
        self.mp_per.set("36"); self.mp_comp.set("12")

    def _clear_pc(self):
        self._set([self.pc_n1,self.pc_n2],"")
        self._set([self.pc_res_v],"—")
    def _sample_pc(self):
        self.pc_n1.set("32.42"); self.pc_n2.set("21.27")

    def _clear_po(self):
        self._set([self.pon_pct,self.pon_num],"")
        self._set([self.pon_res_v],"—")
    def _sample_po(self):
        self.pon_pct.set("10"); self.pon_num.set("25")

    def _calc_interest_rate(self):
        try:
            loan  = float(self.ir_loan.get().replace(",", ""))
            pmt   = float(self.ir_payment.get().replace(",", ""))
            nper  = int(self.ir_periods.get())
            comp  = int(self.ir_comp.get())
            rate  = calc_rate(nper, pmt, loan, comp)
            if rate is None: raise ValueError
            rpp   = rate / comp
            iamt  = cumipmt(rpp, nper, loan)
            pamt  = cumprinc(rpp, nper, loan)
            self.ir_rate_v.set(fmt_pct(rate))
            self.ir_int_v.set(fmt_currency(iamt))
            self.ir_princ_v.set(fmt_currency(pamt))
            self.ir_total_v.set(fmt_currency(iamt + pamt))
        except Exception:
            self.ir_rate_v.set("Error — check inputs")

    def _build_monthly_payment(self, parent):
        card = make_card(parent)
        card.pack(side="left", fill="both", expand=True, padx=(8, 0))
        section_header(card, "  CALCULATE MONTHLY PAYMENT")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.mp_loan = labeled_entry(inner, "Loan Amount ($)",        "21303.60", on_enter=self._calc_monthly_payment)
        self.mp_rate = labeled_entry(inner, "Annual Interest Rate (%)", "8.741",    on_enter=self._calc_monthly_payment)
        self.mp_per  = labeled_entry(inner, "Periods (months)",        "36",        on_enter=self._calc_monthly_payment)
        self.mp_comp = labeled_entry(inner, "Compounding Periods/yr",  "12",        on_enter=self._calc_monthly_payment)

        calc_button(inner, "Calculate →", self._calc_monthly_payment, clear_cmd=self._clear_mp, sample_cmd=self._sample_mp)

        res = ctk.CTkFrame(card, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.mp_pmt_v   = tk.StringVar(value="—")
        self.mp_int_v   = tk.StringVar(value="—")
        self.mp_princ_v = tk.StringVar(value="—")
        self.mp_total_v = tk.StringVar(value="—")
        result_row(res, "Monthly Payment",       self.mp_pmt_v,   color=ACCENT)
        result_row(res, "Total Interest Amount", self.mp_int_v)
        result_row(res, "Total Principal",       self.mp_princ_v)
        result_row(res, "Total Payment Amount",  self.mp_total_v)

    def _calc_monthly_payment(self):
        try:
            loan = float(self.mp_loan.get().replace(",", ""))
            rate = float(self.mp_rate.get().replace(",", "")) / 100
            nper = int(self.mp_per.get())
            comp = int(self.mp_comp.get())
            pmt  = calc_pmt(rate, nper, loan, comp)
            if pmt is None: raise ValueError
            rpp  = rate / comp
            iamt = cumipmt(rpp, nper, loan)
            pamt = cumprinc(rpp, nper, loan)
            self.mp_pmt_v.set(fmt_currency(pmt))
            self.mp_int_v.set(fmt_currency(iamt))
            self.mp_princ_v.set(fmt_currency(pamt))
            self.mp_total_v.set(fmt_currency(iamt + pamt))
        except Exception:
            self.mp_pmt_v.set("Error — check inputs")

    def _build_percent_section(self):
        cols = ctk.CTkFrame(self, fg_color="transparent")
        cols.pack(fill="x", padx=20, pady=(8, 16))

        # Percent change
        card1 = make_card(cols)
        card1.pack(side="left", fill="both", expand=True, padx=(0, 8))
        section_header(card1, "  PERCENT INCREASE / DECREASE")
        inner1 = ctk.CTkFrame(card1, fg_color="transparent")
        inner1.pack(fill="x", padx=16, pady=(0, 8))
        self.pc_n1 = labeled_entry(inner1, "Number One", "32.42", on_enter=self._calc_pct_change)
        self.pc_n2 = labeled_entry(inner1, "Number Two", "21.27", on_enter=self._calc_pct_change)
        calc_button(inner1, "Calculate →", self._calc_pct_change, clear_cmd=self._clear_pc, sample_cmd=self._sample_pc)
        res1 = ctk.CTkFrame(card1, fg_color="transparent")
        res1.pack(fill="x", padx=16, pady=(0, 16))
        self.pc_res_v = tk.StringVar(value="—")
        result_row(res1, "Percent Increase / Decrease", self.pc_res_v, color=ACCENT)

        # Percent of number
        card2 = make_card(cols)
        card2.pack(side="left", fill="both", expand=True, padx=(8, 0))
        section_header(card2, "  PERCENT OF A NUMBER")
        inner2 = ctk.CTkFrame(card2, fg_color="transparent")
        inner2.pack(fill="x", padx=16, pady=(0, 8))
        self.pon_pct = labeled_entry(inner2, "Percent (%)", "10",  on_enter=self._calc_pct_of)
        self.pon_num = labeled_entry(inner2, "Of (number)", "25", on_enter=self._calc_pct_of)
        calc_button(inner2, "Calculate →", self._calc_pct_of, clear_cmd=self._clear_po, sample_cmd=self._sample_po)
        res2 = ctk.CTkFrame(card2, fg_color="transparent")
        res2.pack(fill="x", padx=16, pady=(0, 16))
        self.pon_res_v = tk.StringVar(value="—")
        result_row(res2, "Percent of Number", self.pon_res_v, color=ACCENT)

    def _calc_pct_change(self):
        try:
            n1 = float(self.pc_n1.get())
            n2 = float(self.pc_n2.get())
            r  = (n1 - n2) / n1
            self.pc_res_v.set(f"{r * 100:.4f}%  ({'increase' if r > 0 else 'decrease'})")
        except Exception:
            self.pc_res_v.set("Error")

    def _calc_pct_of(self):
        try:
            pct = float(self.pon_pct.get()) / 100
            num = float(self.pon_num.get())
            self.pon_res_v.set(fmt_num(pct * num))
        except Exception:
            self.pon_res_v.set("Error")


# ─────────────────────────────────────────────────────────
# TAB 2 — PICTURE FRAME SPACING
# ─────────────────────────────────────────────────────────

    def _calculate(self):
        """Run all four loan sub-calculators at once when Enter is pressed."""
        try: self._calc_interest_rate()
        except Exception: pass
        try: self._calc_monthly_payment()
        except Exception: pass
        try: self._calc_pct_change()
        except Exception: pass
        try: self._calc_pct_of()
        except Exception: pass


class FrameSpacingTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Picture Frame Spacing",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)


        # ── INPUTS (full width) ──────────────────────────────
        card_in = make_card(self)
        card_in.pack(fill="x", padx=20, pady=(0, 10))
        section_header(card_in, "  INPUTS")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 12))

        self.fs_count = labeled_entry(inner, "Number of Frames", "4", on_enter=self._calculate)
        self.fs_wall, _, _ = self._inch_entry(inner, "Total Wall Length (inches)", "192.1")
        self.fs_width, _, _ = self._inch_entry(inner, "Single Frame Width (inches)", "24")
        calc_button(inner, "Calculate Spacing →", self._calculate, clear_cmd=self._clear_fs, sample_cmd=self._sample_fs)

        # ── RESULTS (full width, below inputs) ───────────────
        card_out = make_card(self)
        card_out.pack(fill="x", padx=20, pady=(0, 16))
        section_header(card_out, "  RESULTS")
        res = ctk.CTkFrame(card_out, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 12))

        def res3(lbl, v1, v2, v3):
            row = ctk.CTkFrame(res, fg_color=RES_BG, corner_radius=6, height=34)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=lbl, font=ctk.CTkFont("Segoe UI", 10),
                         text_color=MUTED, width=240, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(row, textvariable=v1,
                         font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=ACCENT, width=90).pack(side="left")
            ctk.CTkLabel(row, textvariable=v2,
                         font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT, width=100).pack(side="left")
            ctk.CTkLabel(row, textvariable=v3,
                         font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED, width=120).pack(side="left")

        # Column headers
        hdr = ctk.CTkFrame(res, fg_color="transparent")
        hdr.pack(fill="x", pady=(4, 2))
        for txt, w in [("Measurement", 240), ("Decimal (in)", 90), ("Ruler (in)", 100), ("Feet | In", 120)]:
            ctk.CTkLabel(hdr, text=txt, font=ctk.CTkFont("Segoe UI", 9, "bold"),
                         text_color=MUTED, width=w,
                         anchor="w" if txt == "Measurement" else "e").pack(
                         side="left", padx=(10 if txt == "Measurement" else 0, 0))

        self.fs_space_d = tk.StringVar(value="—"); self.fs_space_r = tk.StringVar(value="—"); self.fs_space_f = tk.StringVar(value="—")
        self.fs_first_d = tk.StringVar(value="—"); self.fs_first_r = tk.StringVar(value="—"); self.fs_first_f = tk.StringVar(value="—")
        self.fs_next_d  = tk.StringVar(value="—"); self.fs_next_r  = tk.StringVar(value="—"); self.fs_next_f  = tk.StringVar(value="—")
        self.fs_last_d  = tk.StringVar(value="—"); self.fs_last_r  = tk.StringVar(value="—"); self.fs_last_f  = tk.StringVar(value="—")
        self.fs_check_v = tk.StringVar(value="")

        res3("Spacing Between Frames",         self.fs_space_d, self.fs_space_r, self.fs_space_f)
        res3("Distance to Center of Frame #1", self.fs_first_d, self.fs_first_r, self.fs_first_f)

        self.fs_next_row_lbl = tk.StringVar(value="Distance to Center of Next Frames")
        row_n = ctk.CTkFrame(res, fg_color=RES_BG, corner_radius=6, height=34)
        row_n.pack(fill="x", pady=2)
        row_n.pack_propagate(False)
        ctk.CTkLabel(row_n, textvariable=self.fs_next_row_lbl,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED,
                     width=240, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(row_n, textvariable=self.fs_next_d,
                     font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=ACCENT, width=90).pack(side="left")
        ctk.CTkLabel(row_n, textvariable=self.fs_next_r,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT, width=100).pack(side="left")
        ctk.CTkLabel(row_n, textvariable=self.fs_next_f,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED, width=120).pack(side="left")

        self.fs_last_row_lbl = tk.StringVar(value="Distance from Last Frame to End")
        row_l = ctk.CTkFrame(res, fg_color=RES_BG, corner_radius=6, height=34)
        row_l.pack(fill="x", pady=2)
        row_l.pack_propagate(False)
        ctk.CTkLabel(row_l, textvariable=self.fs_last_row_lbl,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED,
                     width=240, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(row_l, textvariable=self.fs_last_d,
                     font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=ACCENT, width=90).pack(side="left")
        ctk.CTkLabel(row_l, textvariable=self.fs_last_r,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT, width=100).pack(side="left")
        ctk.CTkLabel(row_l, textvariable=self.fs_last_f,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED, width=120).pack(side="left")

        ck = ctk.CTkFrame(res, fg_color="transparent")
        ck.pack(fill="x", pady=(6, 4))
        ctk.CTkLabel(ck, textvariable=self.fs_check_v,
                     font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=SUCCESS).pack(anchor="e", padx=10)

        ctk.CTkLabel(card_out, text="* Ruler values rounded to nearest 1/16\"",
                     font=ctk.CTkFont("Segoe UI", 8), text_color=MUTED).pack(anchor="e", padx=16, pady=(0, 8))

        # ── DIAGRAM (full width, below results) ──────────────
        card_diag = make_card(self)
        card_diag.pack(fill="x", padx=20, pady=(0, 20))
        section_header(card_diag, "  LIVE DIAGRAM")
        self.fs_canvas = tk.Canvas(card_diag, height=240, bg=CARD,
                                   highlightthickness=0)
        self.fs_canvas.pack(fill="x", padx=16, pady=(0, 16))
        self._last_diag = None
        self._canvas_w  = 0
        self.fs_canvas.bind("<Configure>", self._on_canvas_configure)

    def _inch_entry(self, parent, label, default):
        """Entry with live ruler (in) and feet|in labels that update as you type."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", 10),
                     text_color=TEXT, width=220, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(default))
        ent = ctk.CTkEntry(row, textvariable=var, width=80,
                           fg_color=INPUT_BG, border_color=INPUT_BORDER,
                           font=ctk.CTkFont("Segoe UI", 10))
        ent.pack(side="left", padx=(8, 0))

        ruler_var = tk.StringVar(value="")
        feet_var  = tk.StringVar(value="")

        ctk.CTkLabel(row, textvariable=feet_var,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=ACCENT,
                     width=130, anchor="w").pack(side="left", padx=(10, 0))

        def _update(*_):
            try:
                v = float(var.get())
                ruler_var.set(inches_to_ruler(v))
                feet_var.set(inches_to_feet(v))
            except ValueError:
                ruler_var.set("")
                feet_var.set("")

        var.trace_add("write", _update)
        _update()
        ent.bind("<Return>", lambda e: self._calculate())
        return var, ruler_var, feet_var

    def _on_canvas_configure(self, event):
        """Store actual canvas width from event, then redraw."""
        self._canvas_w = event.width
        if self._last_diag:
            self._draw_diagram(*self._last_diag)
        else:
            self._draw_diagram(None, None, None)

    def _draw_diagram(self, count, wall, width):
        """Draw wall diagram using width captured from Configure event."""
        c = self.fs_canvas
        c.delete("all")
        W = getattr(self, "_canvas_w", None) or c.winfo_width()
        if not W or W < 50:
            W = 700
        H = 240

        if count is None:
            c.create_text(W // 2, H // 2,
                          text="Enter values and click  Calculate Spacing →",
                          fill=MUTED, font=("Segoe UI", 10))
            return

        PAD    = 50
        # Layout (top → bottom): center-meas row, frame labels, frames,
        #                         spacing arrows, wall line, wall label
        CONTENT_H = 145
        OFFSET    = (H - CONTENT_H) // 2
        MEAS_Y = OFFSET            # center-measurement arrows (new, top row)
        TOP    = MEAS_Y + 38       # top of frames (labels sit between MEAS_Y and TOP)
        BOT    = TOP + 35          # frames are 35 px tall
        MID    = (TOP + BOT) // 2
        ARW_Y  = BOT + 28          # spacing arrows below frames
        WALL_Y = ARW_Y + 22        # wall line
        # wall label at WALL_Y + 12

        draw_w     = W - 2 * PAD
        scale      = draw_w / wall
        frame_px   = width * scale
        spacing    = (wall - count * width) / (count + 1)
        spacing_px = spacing * scale
        first      = spacing + width / 2          # wall edge → center frame 1
        nxt        = spacing + width              # center frame 1 → center frame 2

        # pixel positions of key centres
        cx1 = PAD + spacing_px + frame_px / 2    # centre of frame 1
        cx2 = cx1 + spacing_px + frame_px         # centre of frame 2

        # ── Center measurement arrows (top row, green) ────────
        CLR_MEAS = "#276749"   # green — distinct from navy spacing arrows
        TICK_H   = 6

        def tick(xp, y):
            c.create_line(xp, y - TICK_H, xp, y + TICK_H, fill=CLR_MEAS, width=1)

        # Arrow 1: wall left → centre of frame 1
        tick(PAD, MEAS_Y)
        tick(cx1, MEAS_Y)
        c.create_line(PAD + 2, MEAS_Y, cx1 - 2, MEAS_Y,
                      fill=CLR_MEAS, width=1, arrow="both")
        if cx1 - PAD > 20:
            c.create_text((PAD + cx1) / 2, MEAS_Y - 9,
                          text=inches_to_ruler(first),
                          fill=CLR_MEAS, font=("Segoe UI", 8))

        # Arrow 2: centre frame 1 → centre frame 2 (only if ≥2 frames)
        if count >= 2:
            tick(cx2, MEAS_Y)
            c.create_line(cx1 + 2, MEAS_Y, cx2 - 2, MEAS_Y,
                          fill=CLR_MEAS, width=1, arrow="both")
            if cx2 - cx1 > 20:
                c.create_text((cx1 + cx2) / 2, MEAS_Y - 9,
                              text=inches_to_ruler(nxt),
                              fill=CLR_MEAS, font=("Segoe UI", 8))

        # ── Wall (thin reference line) ────────────────────────
        c.create_line(PAD, WALL_Y, W - PAD, WALL_Y, fill="#555", width=2)
        c.create_line(PAD,     WALL_Y - 5, PAD,     WALL_Y + 5, fill="#555", width=2)
        c.create_line(W - PAD, WALL_Y - 5, W - PAD, WALL_Y + 5, fill="#555", width=2)
        c.create_text(W // 2, WALL_Y + 12,
                      text=f"Wall: {inches_to_ruler(wall)}  ({inches_to_feet(wall)})",
                      fill=MUTED, font=("Segoe UI", 8))

        x = PAD + spacing_px

        for i in range(count):
            x0, x1 = x, x + frame_px
            cx = (x0 + x1) / 2

            # Frame rectangle
            c.create_rectangle(x0, TOP, x1, BOT,
                                fill=RES_BG, outline="#1565C0", width=3)
            c.create_text(cx, MID, text=str(i + 1),
                          fill="#1565C0", font=("Segoe UI", 10, "bold"))
            if frame_px > 28:
                c.create_text(cx, TOP - 11,
                              text=inches_to_ruler(width),
                              fill="#333", font=("Segoe UI", 8))

            # Spacing arrow before this frame
            sx0, sx1 = x0 - spacing_px, x0
            scx = (sx0 + sx1) / 2
            if spacing_px > 12:
                c.create_line(sx0 + 3, ARW_Y, sx1 - 3, ARW_Y,
                              fill="#1F3864", width=1, arrow="both")
            if spacing_px > 28:
                c.create_text(scx, ARW_Y - 9,
                              text=inches_to_ruler(spacing),
                              fill="#1F3864", font=("Segoe UI", 8))

            x += frame_px + spacing_px

        # Last spacing arrow (after final frame)
        sx0, sx1 = x - spacing_px, W - PAD
        scx = (sx0 + sx1) / 2
        if spacing_px > 12:
            c.create_line(sx0 + 3, ARW_Y, sx1 - 3, ARW_Y,
                          fill="#1F3864", width=1, arrow="both")
        if spacing_px > 28:
            c.create_text(scx, ARW_Y - 9,
                          text=inches_to_ruler(spacing),
                          fill="#1F3864", font=("Segoe UI", 8))

    def _sample_fs(self):
        self.fs_count.set("4"); self.fs_wall.set("192.1"); self.fs_width.set("24")

    def _clear_fs(self):
        for v in [self.fs_count, self.fs_wall, self.fs_width]:
            v.set("")
        for v in [self.fs_space_d, self.fs_space_r, self.fs_space_f,
                  self.fs_first_d, self.fs_first_r, self.fs_first_f,
                  self.fs_next_d,  self.fs_next_r,  self.fs_next_f,
                  self.fs_last_d,  self.fs_last_r,  self.fs_last_f]:
            v.set("—")
        self.fs_check_v.set("")
        self.fs_canvas.delete("all")

    def _calculate(self):
        try:
            count = int(self.fs_count.get())
            wall  = float(self.fs_wall.get())
            width = float(self.fs_width.get())

            spacing = (wall - count * width) / (count + 1)
            first   = spacing + width / 2
            nxt     = spacing + width
            last    = first

            def s(v): return (f"{v:.3f}", inches_to_ruler(v), inches_to_feet(v))

            sp = s(spacing)
            fi = s(first)
            nx = s(nxt)
            la = s(last)

            self.fs_space_d.set(sp[0]); self.fs_space_r.set(sp[1]); self.fs_space_f.set(sp[2])
            self.fs_first_d.set(fi[0]); self.fs_first_r.set(fi[1]); self.fs_first_f.set(fi[2])
            self.fs_next_d.set(nx[0]);  self.fs_next_r.set(nx[1]);  self.fs_next_f.set(nx[2])
            self.fs_last_d.set(la[0]);  self.fs_last_r.set(la[1]);  self.fs_last_f.set(la[2])

            self.fs_next_row_lbl.set(f"Distance to Center of Next {count - 1} Frame(s)")
            self.fs_last_row_lbl.set(f"Distance from Frame #{count} to End")

            check = (first + nxt * (count - 1) + last) - wall
            self.fs_check_v.set("✓  Everything ties!" if abs(check) < 0.001 else f"⚠  Check: off by {check:.4f}\"")
            self._last_diag = (count, wall, width)
        except Exception:
            self.fs_space_d.set("Error — check inputs")
            return
        self._draw_diagram(count, wall, width)


# ─────────────────────────────────────────────────────────
# TAB 3 — BASIC DEPRECIATION
# ─────────────────────────────────────────────────────────

class BasicDepreciationTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Basic Depreciation Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)
        tk.Label(self, text="For illustration only — not for tax reporting.",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=(0, 10))

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20)

        card_in = make_card(top)
        card_in.pack(side="left", fill="y", padx=(0, 12), ipadx=8)
        section_header(card_in, "  ASSET INFORMATION")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.bd_desc    = labeled_entry(inner, "Asset Description",     "", on_enter=self._calculate)
        self.bd_price   = labeled_entry(inner, "Purchase Price ($)",    "9000", on_enter=self._calculate)
        self.bd_salvage = labeled_entry(inner, "Salvage Value ($)",     "200", on_enter=self._calculate)
        self.bd_period  = labeled_entry(inner, "Depreciation Period (yrs)", "5", on_enter=self._calculate)
        self.bd_method  = labeled_option(inner, "Depreciation Method", ["DB", "SL", "SYOD"], "DB")
        self.bd_factor  = labeled_entry(inner, "DB Factor (for DB)",   "2", on_enter=self._calculate)

        calc_button(inner, "Generate Schedule →", self._calculate, clear_cmd=self._clear, sample_cmd=self._sample)

        card_sum = make_card(top)
        card_sum.pack(side="left", fill="y")
        section_header(card_sum, "  SUMMARY")
        res = ctk.CTkFrame(card_sum, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.bd_tot_depr = tk.StringVar(value="—")
        self.bd_tot_bv   = tk.StringVar(value="—")
        result_row(res, "Total Depreciation", self.bd_tot_depr, color=ACCENT)
        result_row(res, "Final Book Value",   self.bd_tot_bv)

        # Table
        tbl_card = make_card(self)
        tbl_card.pack(fill="x", padx=20, pady=(10, 16))
        section_header(tbl_card, "  DEPRECIATION SCHEDULE")
        cols = ("Year", "Depreciation", "Cumulative", "Book Value")
        widths = (60, 130, 130, 130)
        tbl_frame, self.bd_tree = make_table(tbl_card, cols, widths, height=12)
        tbl_frame.pack(fill="x", padx=16, pady=(0, 16))
        # ── Method legend ─────────────────────────────────────────────
        leg = ctk.CTkFrame(self, fg_color=RES_BG, corner_radius=8)
        leg.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(leg, text="📖  Method Guide",
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(8,2))
        legend_text = (
            "DB  (Declining Balance)  —  Accelerated method. Each year deducts (100% / life × DB Factor) of remaining book value. "
            "DB Factor 2 = Double Declining Balance (DDB), the most common. Automatically switches to Straight-Line when SL gives a larger deduction.\n\n"
            "SL  (Straight-Line)  —  Equal deduction every year: (Cost − Salvage) ÷ Life. Simple and predictable.\n\n"
            "SYOD  (Sum of Years' Digits)  —  Accelerated method. Each year's fraction = remaining useful life ÷ sum of all years' digits. "
            "Example for 5-year life: digits sum = 1+2+3+4+5 = 15. Year 1 gets 5/15, Year 2 gets 4/15, etc."
        )
        tk.Label(leg, text=legend_text, font=("Segoe UI", 9), fg=TEXT, bg=RES_BG,
                 justify="left", anchor="w", wraplength=700
                 ).pack(anchor="w", padx=14, pady=(0, 10))

    def _clear(self):
        for v in [self.bd_desc,self.bd_price,self.bd_salvage,
                  self.bd_period,self.bd_factor]: v.set("")
        for v in [self.bd_tot_depr,self.bd_tot_bv]: v.set("—")
        for _i in list(self.bd_tree.get_children('')): self.bd_tree.delete(_i)

    def _sample(self):
        self.bd_desc.set(""); self.bd_price.set("9000")
        self.bd_salvage.set("200"); self.bd_period.set("5")
        self.bd_factor.set("2")


    def _calculate(self):
        try:
            cost    = float(self.bd_price.get().replace(",", ""))
            salvage = float(self.bd_salvage.get().replace(",", ""))
            life    = int(self.bd_period.get())
            method  = self.bd_method.get()
            factor  = float(self.bd_factor.get())

            rows = basic_depreciation_schedule(cost, salvage, life, method, factor)

            for _i in list(self.bd_tree.get_children('')): self.bd_tree.delete(_i)
            for i, (yr, d, cum, bv) in enumerate(rows):
                tag = "alt" if i % 2 else ""
                self.bd_tree.insert("", "end", values=(
                    yr,
                    f"${d:,.2f}",
                    f"${cum:,.2f}",
                    f"${bv:,.2f}",
                ), tags=(tag,))

            self.bd_tot_depr.set(fmt_currency(rows[-1][2]))
            self.bd_tot_bv.set(fmt_currency(rows[-1][3]))
        except Exception as e:
            self.bd_tot_depr.set(f"Error: {e}")


# ─────────────────────────────────────────────────────────
# TAB 4 — MACRS RATE CALCULATOR
# ─────────────────────────────────────────────────────────

class MacrsRateTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(self._scroll, text="MACRS Depreciation Rate Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self._scroll, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)
        tk.Label(self._scroll, text="For illustration only — rates may vary ±0.01% from official IRS tables. Not for tax reporting.",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=(0, 10))

        top = ctk.CTkFrame(self._scroll, fg_color="transparent")
        top.pack(fill="x", padx=20)

        card_in = make_card(top)
        card_in.pack(side="left", fill="y", padx=(0, 12), ipadx=8)
        section_header(card_in, "  ASSET INFORMATION")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.mr_basis   = labeled_entry(inner, "Depreciation Basis ($)",     "1000", on_enter=self._calculate)
        self.mr_period  = labeled_entry(inner, "Recovery Period (yrs)",       "5", on_enter=self._calculate)
        self.mr_method  = labeled_option(inner, "Method", ["DB-SL", "SL"], "DB-SL")
        self.mr_factor  = labeled_entry(inner, "DB Factor",                  "2", on_enter=self._calculate)
        self.mr_conv    = labeled_option(inner, "Convention",
                                         ["Half-Year", "Mid-Quarter", "Mid-Month"], "Half-Year")
        self.mr_placed  = labeled_entry(inner, "Placed in Service (qtr/mo)", "4", on_enter=self._calculate)

        calc_button(inner, "Generate Schedule →", self._calculate, clear_cmd=self._clear, sample_cmd=self._sample)

        card_sum = make_card(top)
        card_sum.pack(side="left", fill="y")
        section_header(card_sum, "  SUMMARY")
        res = ctk.CTkFrame(card_sum, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.mr_last_yr = tk.StringVar(value="—")
        self.mr_tot_dep = tk.StringVar(value="—")
        result_row(res, "Last Year of Depreciation", self.mr_last_yr)
        result_row(res, "Total Depreciation",        self.mr_tot_dep, color=ACCENT)

        tbl_card = make_card(self._scroll)
        tbl_card.pack(fill="x", padx=20, pady=(10, 16))
        section_header(tbl_card, "  DEPRECIATION SCHEDULE")
        cols = ("Year", "Depreciation", "Cumulative", "Book Value", "Rate (dj)")
        widths = (60, 120, 120, 120, 100)
        tbl_frame, self.mr_tree = make_table(tbl_card, cols, widths, height=12)
        tbl_frame.pack(fill="x", padx=16, pady=(0, 16))
        # ── MACRS legend ───────────────────────────────────────────────
        mleg = ctk.CTkFrame(self._scroll, fg_color=RES_BG, corner_radius=8)
        mleg.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(mleg, text="📖  MACRS Guide",
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(8,2))
        mleg_text = (
            "MACRS  (Modified Accelerated Cost Recovery System)  —  The IRS-required depreciation method for U.S. business assets placed in service after 1986 (IRC §168).\n\n"
            "DB-SL  —  Starts with Declining Balance (200% DB = double-declining) then switches to Straight-Line when SL gives a higher deduction. "
            "This is the standard GDS (General Depreciation System) method for most personal property.\n\n"
            "SL  —  Straight-Line over the recovery period. Required for ADS (Alternative Depreciation System) and some asset classes.\n\n"
            "DB Factor:  2 = 200% DB (most personal property)  |  1.5 = 150% DB (farming / ADS)  |  1 = Straight-Line\n\n"
            "Conventions:\n"
            "  Half-Year (HY)  —  All assets treated as placed in service at mid-year regardless of actual date. Most common.\n"
            "  Mid-Quarter (MQ)  —  Required when >40% of annual acquisitions occur in Q4. Uses mid-quarter of the actual quarter.\n"
            "  Mid-Month (MM)  —  Used only for residential rental (27.5 yr) and nonresidential real property (39 yr)."
        )
        tk.Label(mleg, text=mleg_text, font=("Segoe UI", 9), fg=TEXT, bg=RES_BG,
                 justify="left", anchor="w", wraplength=700
                 ).pack(anchor="w", padx=14, pady=(0, 10))

    def _clear(self):
        for v in [self.mr_basis,self.mr_period,self.mr_factor,self.mr_placed]: v.set("")
        for v in [self.mr_last_yr,self.mr_tot_dep]: v.set("—")
        for _i in list(self.mr_tree.get_children('')): self.mr_tree.delete(_i)

    def _sample(self):
        self.mr_basis.set("1000"); self.mr_period.set("5")
        self.mr_factor.set("2"); self.mr_placed.set("4")


    def _calculate(self):
        try:
            basis  = float(self.mr_basis.get().replace(",", ""))
            n      = int(self.mr_period.get())
            method = self.mr_method.get()
            factor = float(self.mr_factor.get())
            conv   = self.mr_conv.get()
            placed = float(self.mr_placed.get())

            rows = macrs_schedule(basis, n, method, factor, conv, placed)

            for _i in list(self.mr_tree.get_children('')): self.mr_tree.delete(_i)
            for i, r in enumerate(rows):
                tag = "alt" if i % 2 else ""
                self.mr_tree.insert("", "end", values=(
                    r["year"],
                    f"${r['depreciation']:,.2f}",
                    f"${r['cumulative']:,.2f}",
                    f"${r['book_value']:,.2f}",
                    f"{r['rate']*100:.2f}%",
                ), tags=(tag,))

            if rows:
                self.mr_last_yr.set(str(rows[-1]["year"]))
                self.mr_tot_dep.set(fmt_currency(rows[-1]["cumulative"]))
        except Exception as e:
            self.mr_last_yr.set(f"Error: {e}")


# ─────────────────────────────────────────────────────────
# TAB 5 — MACRS FULL CALCULATOR
# ─────────────────────────────────────────────────────────

class MacrsFullTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(self._scroll, text="MACRS Depreciation Calculator (with Adjustments)",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self._scroll, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)
        tk.Label(self._scroll, text="Supports per-year basis adjustments. Not for official tax reporting.",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=(0, 10))

        top = ctk.CTkFrame(self._scroll, fg_color="transparent")
        top.pack(fill="x", padx=20)

        card_in = make_card(top)
        card_in.pack(side="left", fill="y", padx=(0, 12), ipadx=8)
        section_header(card_in, "  ASSET INFORMATION")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.mf_basis  = labeled_entry(inner, "Depreciation Basis ($)",      "7500", on_enter=self._calculate)
        self.mf_period = labeled_entry(inner, "Recovery Period (yrs)",         "7", on_enter=self._calculate)
        self.mf_method = labeled_option(inner, "Method", ["DB-SL", "SL"], "SL")
        self.mf_factor = labeled_entry(inner, "DB Factor",                    "2", on_enter=self._calculate)
        self.mf_conv   = labeled_option(inner, "Convention",
                                         ["Half-Year", "Mid-Quarter", "Mid-Month"], "Half-Year")
        self.mf_placed = labeled_entry(inner, "Placed in Service (qtr/mo)",  "1", on_enter=self._calculate)
        self.mf_adj    = labeled_entry(inner, "Adjustments (yr:amt, ...)",   "2:500", on_enter=self._calculate)
        ctk.CTkLabel(inner, text="  e.g.  2:500, 4:-200",
                     font=ctk.CTkFont("Segoe UI", 8), text_color=MUTED).pack(anchor="w")

        calc_button(inner, "Generate Schedule →", self._calculate, clear_cmd=self._clear, sample_cmd=self._sample)

        card_sum = make_card(top)
        card_sum.pack(side="left", fill="y")
        section_header(card_sum, "  SUMMARY")
        res = ctk.CTkFrame(card_sum, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.mf_last   = tk.StringVar(value="—")
        self.mf_first  = tk.StringVar(value="—")
        self.mf_total  = tk.StringVar(value="—")
        result_row(res, "Last Year",         self.mf_last)
        result_row(res, "First Yr Fraction", self.mf_first)
        result_row(res, "Total Depreciation",self.mf_total, color=ACCENT)

        tbl_card = make_card(self._scroll)
        tbl_card.pack(fill="x", padx=20, pady=(10, 16))
        section_header(tbl_card, "  DEPRECIATION SCHEDULE")
        cols = ("Year", "Adjustments", "Basis", "Dj (SL)", "Dj (DB)", "Depreciation", "Cumulative", "Book Value")
        widths = (50, 90, 90, 90, 90, 100, 100, 100)
        tbl_frame, self.mf_tree = make_table(tbl_card, cols, widths, height=12)
        tbl_frame.pack(fill="x", padx=16, pady=(0, 16))
        # ── MACRS legend ───────────────────────────────────────────────
        mleg = ctk.CTkFrame(self._scroll, fg_color=RES_BG, corner_radius=8)
        mleg.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(mleg, text="📖  MACRS Guide",
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=14, pady=(8,2))
        mleg_text = (
            "MACRS  (Modified Accelerated Cost Recovery System)  —  The IRS-required depreciation method for U.S. business assets placed in service after 1986 (IRC §168).\n\n"
            "DB-SL  —  Starts with Declining Balance (200% DB = double-declining) then switches to Straight-Line when SL gives a higher deduction. "
            "This is the standard GDS (General Depreciation System) method for most personal property.\n\n"
            "SL  —  Straight-Line over the recovery period. Required for ADS (Alternative Depreciation System) and some asset classes.\n\n"
            "DB Factor:  2 = 200% DB (most personal property)  |  1.5 = 150% DB (farming / ADS)  |  1 = Straight-Line\n\n"
            "Conventions:\n"
            "  Half-Year (HY)  —  All assets treated as placed in service at mid-year regardless of actual date. Most common.\n"
            "  Mid-Quarter (MQ)  —  Required when >40% of annual acquisitions occur in Q4. Uses mid-quarter of the actual quarter.\n"
            "  Mid-Month (MM)  —  Used only for residential rental (27.5 yr) and nonresidential real property (39 yr)."
        )
        tk.Label(mleg, text=mleg_text, font=("Segoe UI", 9), fg=TEXT, bg=RES_BG,
                 justify="left", anchor="w", wraplength=700
                 ).pack(anchor="w", padx=14, pady=(0, 10))

    def _parse_adjustments(self, text):
        adj = {}
        text = text.strip()
        if not text:
            return adj
        for part in text.split(","):
            part = part.strip()
            if ":" in part:
                yr, val = part.split(":", 1)
                adj[int(yr.strip())] = float(val.strip())
        return adj

    def _clear(self):
        for v in [self.mf_basis,self.mf_period,self.mf_factor,
                  self.mf_placed,self.mf_adj]: v.set("")
        for v in [self.mf_last,self.mf_first,self.mf_total]: v.set("—")
        for _i in list(self.mf_tree.get_children('')): self.mf_tree.delete(_i)

    def _sample(self):
        self.mf_basis.set("7500"); self.mf_period.set("7")
        self.mf_factor.set("2"); self.mf_placed.set("1")
        self.mf_adj.set("2:500")


    def _calculate(self):
        try:
            basis  = float(self.mf_basis.get().replace(",", ""))
            n      = int(self.mf_period.get())
            method = self.mf_method.get()
            factor = float(self.mf_factor.get())
            conv   = self.mf_conv.get()
            placed = float(self.mf_placed.get())
            adj    = self._parse_adjustments(self.mf_adj.get())

            f1   = macrs_first_year_fraction(conv, placed)
            last = macrs_last_year(n, conv, placed)

            rows = macrs_full_schedule(basis, n, method, factor, conv, placed, adj)

            for _i in list(self.mf_tree.get_children('')): self.mf_tree.delete(_i)
            for i, r in enumerate(rows):
                tag = "alt" if i % 2 else ""
                self.mf_tree.insert("", "end", values=(
                    r["year"],
                    f"${r['adjustment']:,.2f}" if r["adjustment"] else "—",
                    f"${r['basis']:,.2f}",
                    f"${r['dj_sl']:,.2f}" if r["dj_sl"] else "—",
                    f"${r['dj_db']:,.2f}" if r["dj_db"] else "—",
                    f"${r['depreciation']:,.2f}",
                    f"${r['cumulative']:,.2f}",
                    f"${r['book_value']:,.2f}",
                ), tags=(tag,))

            self.mf_last.set(str(last))
            self.mf_first.set(f"{f1 * 100:.1f}%")
            if rows:
                self.mf_total.set(fmt_currency(rows[-1]["cumulative"]))
        except Exception as e:
            self.mf_total.set(f"Error: {e}")


# ─────────────────────────────────────────────────────────
# TAB 6 — MORTGAGE CALCULATOR
# ─────────────────────────────────────────────────────────

class MortgageTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Home Mortgage Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)


        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20)

        # Left: inputs
        card_in = make_card(top)
        card_in.pack(side="left", fill="y", padx=(0, 12), ipadx=8)
        section_header(card_in, "  MORTGAGE INFORMATION")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.mg_loan   = labeled_entry(inner, "Loan Amount ($)",          "250000", on_enter=self._calculate)
        self.mg_rate   = labeled_entry(inner, "Annual Interest Rate (%)", "5.5", on_enter=self._calculate)
        self.mg_years  = labeled_entry(inner, "Term (years)",             "30", on_enter=self._calculate)
        self.mg_freq   = labeled_option(inner, "Payment Frequency",
                                         ["Monthly", "Bi-Weekly", "Weekly"], "Monthly")
        self.mg_extra  = labeled_entry(inner, "Extra Payment ($/period)", "0", on_enter=self._calculate)
        self.mg_tax    = labeled_entry(inner, "Property Tax (% of value)","1.8", on_enter=self._calculate)
        self.mg_ins    = labeled_entry(inner, "Insurance (% of value)",   "0.4", on_enter=self._calculate)
        self.mg_pmi    = labeled_entry(inner, "Monthly PMI ($)",          "80", on_enter=self._calculate)

        calc_button(inner, "Calculate →", self._calculate, clear_cmd=self._clear, sample_cmd=self._sample)

        # Right: results
        card_out = make_card(top)
        card_out.pack(side="left", fill="both", expand=True)
        section_header(card_out, "  RESULTS")
        res = ctk.CTkFrame(card_out, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))

        self.mg_pmt_v   = tk.StringVar(value="—")
        self.mg_piti_v  = tk.StringVar(value="—")
        self.mg_totpmt  = tk.StringVar(value="—")
        self.mg_totint  = tk.StringVar(value="—")
        self.mg_npmt    = tk.StringVar(value="—")
        self.mg_payoff  = tk.StringVar(value="—")

        result_row(res, "Monthly P&I Payment",  self.mg_pmt_v,  color=ACCENT)
        result_row(res, "PITI Payment",          self.mg_piti_v, color=ACCENT)
        result_row(res, "Total Payments",        self.mg_totpmt)
        result_row(res, "Total Interest",        self.mg_totint)
        result_row(res, "Number of Payments",    self.mg_npmt)
        result_row(res, "Payoff Date",           self.mg_payoff)

    def _clear(self):
        for v in [self.mg_loan,self.mg_rate,self.mg_years,
                  self.mg_extra,self.mg_tax,self.mg_ins,self.mg_pmi]: v.set("")
        for v in [self.mg_pmt_v,self.mg_piti_v,self.mg_totpmt,
                  self.mg_totint,self.mg_npmt,self.mg_payoff]: v.set("—")

    def _sample(self):
        self.mg_loan.set("250000"); self.mg_rate.set("5.5")
        self.mg_years.set("30"); self.mg_extra.set("0")
        self.mg_tax.set("1.8"); self.mg_ins.set("0.4")
        self.mg_pmi.set("80")


    def _calculate(self):
        try:
            loan  = float(self.mg_loan.get().replace(",", ""))
            rate  = float(self.mg_rate.get()) / 100
            years = int(self.mg_years.get())
            freq  = self.mg_freq.get()
            extra = float(self.mg_extra.get().replace(",", ""))
            tax   = float(self.mg_tax.get()) / 100
            ins   = float(self.mg_ins.get()) / 100
            pmi   = float(self.mg_pmi.get())

            ppy_map = {"Monthly": 12, "Bi-Weekly": 26, "Weekly": 52}
            ppy = ppy_map[freq]

            base_pmt, schedule = amortization_schedule(loan, rate, years, ppy, extra,
                                                        start_date=date.today())

            total_pmt  = sum(r["payment"] for r in schedule)
            total_int  = sum(r["interest"] for r in schedule)
            n_payments = len(schedule)

            yearly_tax = loan * tax
            yearly_ins = loan * ins
            piti = base_pmt + yearly_tax / ppy + yearly_ins / ppy + pmi * 12 / ppy

            last_date = schedule[-1]["date"] if schedule else "—"

            self.mg_pmt_v.set(fmt_currency(base_pmt))
            self.mg_piti_v.set(fmt_currency(piti))
            self.mg_totpmt.set(fmt_currency(total_pmt))
            self.mg_totint.set(fmt_currency(total_int))
            self.mg_npmt.set(str(n_payments))
            self.mg_payoff.set(last_date)
        except Exception as e:
            self.mg_pmt_v.set(f"Error: {e}")


# ─────────────────────────────────────────────────────────
# TAB 7 — LOAN AMORTIZATION SCHEDULE
# ─────────────────────────────────────────────────────────

class AmortizationTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Loan Amortization Schedule",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=0)


        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20)

        card_in = make_card(top)
        card_in.pack(side="left", fill="y", padx=(0, 12), ipadx=8)
        section_header(card_in, "  LOAN INFORMATION")
        inner = ctk.CTkFrame(card_in, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 8))

        self.am_loan  = labeled_entry(inner, "Loan Amount ($)",            "200000", on_enter=self._calculate)
        self.am_rate  = labeled_entry(inner, "Annual Interest Rate (%)",   "7.0", on_enter=self._calculate)
        self.am_years = labeled_entry(inner, "Term (years)",               "15", on_enter=self._calculate)
        self.am_freq  = labeled_option(inner, "Payment Frequency",
                                        ["Monthly", "Bi-Weekly", "Quarterly"], "Monthly")
        self.am_extra = labeled_entry(inner, "Extra Payment ($/period)",   "0", on_enter=self._calculate)

        calc_button(inner, "Generate Schedule →", self._calculate, clear_cmd=self._clear, sample_cmd=self._sample)

        card_sum = make_card(top)
        card_sum.pack(side="left", fill="y")
        section_header(card_sum, "  SUMMARY")
        res = ctk.CTkFrame(card_sum, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.am_pmt_v  = tk.StringVar(value="—")
        self.am_tot_v  = tk.StringVar(value="—")
        self.am_int_v  = tk.StringVar(value="—")
        self.am_n_v    = tk.StringVar(value="—")
        result_row(res, "Payment Amount",    self.am_pmt_v,  color=ACCENT)
        result_row(res, "Total Payments",    self.am_tot_v)
        result_row(res, "Total Interest",    self.am_int_v)
        result_row(res, "Number of Periods", self.am_n_v)

        tbl_card = make_card(self)
        tbl_card.pack(fill="x", padx=20, pady=(10, 16))
        section_header(tbl_card, "  AMORTIZATION SCHEDULE")
        cols = ("#", "Date", "Payment", "Extra", "Interest", "Principal", "Balance")
        widths = (50, 80, 90, 80, 90, 90, 100)
        tbl_frame, self.am_tree = make_table(tbl_card, cols, widths, height=18)
        tbl_frame.pack(fill="x", padx=16, pady=(0, 16))

    def _clear(self):
        for v in [self.am_loan,self.am_rate,self.am_years,self.am_extra]: v.set("")
        for v in [self.am_pmt_v,self.am_tot_v,self.am_int_v,self.am_n_v]: v.set("—")
        for _i in list(self.am_tree.get_children('')): self.am_tree.delete(_i)

    def _sample(self):
        self.am_loan.set("200000"); self.am_rate.set("7.0")
        self.am_years.set("15"); self.am_extra.set("0")


    def _calculate(self):
        try:
            loan  = float(self.am_loan.get().replace(",", ""))
            rate  = float(self.am_rate.get()) / 100
            years = int(self.am_years.get())
            freq  = self.am_freq.get()
            extra = float(self.am_extra.get().replace(",", ""))

            ppy_map = {"Monthly": 12, "Bi-Weekly": 26, "Quarterly": 4}
            ppy = ppy_map.get(freq, 12)

            base_pmt, schedule = amortization_schedule(loan, rate, years, ppy, extra,
                                                        start_date=date.today())

            for _i in list(self.am_tree.get_children('')): self.am_tree.delete(_i)
            total_pmt = total_int = 0.0
            for i, r in enumerate(schedule):
                tag = "alt" if i % 2 else ""
                self.am_tree.insert("", "end", values=(
                    r["period"],
                    r["date"],
                    f"${r['payment']:,.2f}",
                    f"${r['extra']:,.2f}" if r["extra"] else "—",
                    f"${r['interest']:,.2f}",
                    f"${r['principal']:,.2f}",
                    f"${r['balance']:,.2f}",
                ), tags=(tag,))
                total_pmt += r["payment"]
                total_int += r["interest"]

            self.am_pmt_v.set(fmt_currency(base_pmt))
            self.am_tot_v.set(fmt_currency(total_pmt))
            self.am_int_v.set(fmt_currency(total_int))
            self.am_n_v.set(str(len(schedule)))
        except Exception as e:
            self.am_pmt_v.set(f"Error: {e}")


# ─────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────
# TAB 8 — SCIENTIFIC & GRAPHING CALCULATOR
# ─────────────────────────────────────────────────────────

class ScientificGraphingCalcTab(CalcTabMixin, ctk.CTkFrame):
    _GCOLS = ["#1565C0", "#C62828", "#276749", "#7B1FA2"]

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._current   = "0"
        self._prev      = None
        self._op        = None
        self._new_num   = True
        self._degrees   = True
        self._memory    = 0.0
        self._sci_mem_slots = [None]*8
        self._sci_next_slot = 0
        self._sci_mem_btns  = []
        self._gcanvas_w = 0
        self._gcanvas_h = 0
        self._x_min = -10.0; self._x_max = 10.0
        self._y_min = -10.0; self._y_max = 10.0
        self._drag_start = None
        self._drag_view  = None
        self._fn_vars    = []
        self._build()

    # ── KEYBOARD ─────────────────────────────────────────
    def activate(self):
        self.winfo_toplevel().bind("<Key>", self._on_key)

    def deactivate(self):
        try:
            self.winfo_toplevel().unbind("<Key>")
        except Exception:
            pass

    def _on_key(self, event):
        """Route keyboard to scientific calculator; ignore when in a text entry."""
        if isinstance(event.widget, tk.Entry):
            return
        k = event.keysym
        c = event.char
        if c.isdigit() or k in (
                "KP_0","KP_1","KP_2","KP_3","KP_4",
                "KP_5","KP_6","KP_7","KP_8","KP_9"):
            self._sc_num(c if c.isdigit() else k[-1])
        elif c == "." or k == "KP_Decimal":
            self._sc_dot()
        elif c == "+" or k == "KP_Add":
            self._sc_op_press("+")
        elif c == "-" or k in ("KP_Subtract", "minus"):
            self._sc_op_press("−")
        elif c in ("*", "x") or k == "KP_Multiply":
            self._sc_op_press("×")
        elif c == "/" or k == "KP_Divide":
            self._sc_op_press("÷")
        elif c == "^":
            self._sc_op_press("^")
        elif c == "%":
            self._sc_pct()
        elif k in ("Return", "KP_Enter", "equal"):
            self._sc_equals()
        elif k == "BackSpace":
            self._sc_back()
        elif k == "Escape":
            self._sc_clear()
        elif k == "Delete":
            self._sc_ce()

    # ── BUILD ──────────────────────────────────────────────
    def _build(self):
        ctk.CTkLabel(self, text="Scientific & Graphing Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Overwrite the sample data",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                 anchor="w").pack(anchor="w", padx=20, pady=(0, 8))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sci(body)
        self._build_graph(body)

    # ── SCIENTIFIC CALCULATOR ─────────────────────────────
    def _build_sci(self, parent):
        card = make_card(parent)
        card.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        # Display
        disp = ctk.CTkFrame(card, fg_color=NAV_BG, corner_radius=8)
        disp.pack(fill="x", padx=12, pady=(12, 4))
        hdr = ctk.CTkFrame(disp, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 0))
        self._sci_mem_var   = tk.StringVar(value="")
        self._sci_angle_var = tk.StringVar(value="DEG")
        ctk.CTkLabel(hdr, textvariable=self._sci_mem_var,
                     font=ctk.CTkFont("Segoe UI", 8, "bold"),
                     text_color="#4FC3F7", anchor="w").pack(side="left")
        ctk.CTkLabel(hdr, textvariable=self._sci_angle_var,
                     font=ctk.CTkFont("Segoe UI", 8, "bold"),
                     text_color="#81C784", anchor="e").pack(side="right")
        self._sci_expr_var = tk.StringVar(value="")
        ctk.CTkLabel(disp, textvariable=self._sci_expr_var,
                     font=ctk.CTkFont("Segoe UI", 9), text_color="#7A9CC8",
                     anchor="e").pack(fill="x", padx=10, pady=(2, 0))
        self._sci_disp_var = tk.StringVar(value="0")
        ctk.CTkLabel(disp, textvariable=self._sci_disp_var,
                     font=ctk.CTkFont("Segoe UI", 24, "bold"), text_color="white",
                     anchor="e").pack(fill="x", padx=10, pady=(0, 10))

        def op(s):  return lambda: self._sc_op_press(s)
        def num(d): return lambda: self._sc_num(d)
        def fn(f):  return lambda: self._sc_fn(f)

        ROWS = [
            [("DEG/RAD", self._sc_toggle, "sp"), ("(",  self._sc_lparen, "fn"),
             (")",        self._sc_rparen, "fn"), ("CE", self._sc_ce,    "fn"),
             ("C",        self._sc_clear,  "fn")],
            [("sin",   fn("sin"),  "fn"), ("cos",   fn("cos"),  "fn"), ("tan",  fn("tan"), "fn"),
             ("log",   fn("log"),  "fn"), ("ln",    fn("ln"),   "fn")],
            [("sin⁻¹", fn("asin"), "fn"), ("cos⁻¹", fn("acos"), "fn"), ("tan⁻¹",fn("atan"),"fn"),
             ("10ˣ",   fn("10x"), "fn"), ("eˣ",    fn("ex"),   "fn")],
            [("xʸ",  op("^"),     "op"), ("x²",    fn("sq"),   "fn"), ("x³",  fn("cube"),"fn"),
             ("√x",  fn("sqrt"),  "fn"), ("∛x",    fn("cbrt"), "fn")],
            [("π",   fn("pi"),    "fn"), ("e",     fn("euler"),"fn"), ("|x|", fn("abs"), "fn"),
             ("n!",  fn("fact"),  "fn"), ("1/x",   fn("inv"),  "fn")],
            [("7", num("7"), "num"), ("8", num("8"), "num"), ("9", num("9"), "num"),
             ("÷",  op("÷"), "op"),  ("⌫", self._sc_back,     "fn")],
            [("4", num("4"), "num"), ("5", num("5"), "num"), ("6", num("6"), "num"),
             ("×",  op("×"), "op"),  ("%", self._sc_pct,       "fn")],
            [("1", num("1"), "num"), ("2", num("2"), "num"), ("3", num("3"), "num"),
             ("−",  op("−"), "op"),  ("+/-",self._sc_sign,    "fn")],
            [("0", num("0"), "num"), (".", self._sc_dot, "fn"), ("EXP", self._sc_exp, "fn"),
             ("+",  op("+"), "op"),  ("=", self._sc_equals,   "eq")],
        ]
        STY = {
            "eq":  (ACCENT,   "white", "#0D47A1"),
            "op":  (NAV_ACT,  "white", NAV_HOV),
            "sp":  ("#276749","white", "#1A4D30"),
            "fn":  ("#D6E4F0", NAV_BG, "#B8CCE4"),
            "num": ("#F0F4F8", TEXT,   "#D6E4F0"),
        }
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(padx=12, pady=(2, 12))
        for r, row in enumerate(ROWS):
            for c, (lbl, cmd, sty) in enumerate(row):
                bg, fg, hov = STY[sty]
                ctk.CTkButton(grid, text=lbl, command=cmd,
                              width=58, height=42, fg_color=bg,
                              hover_color=hov, text_color=fg,
                              font=ctk.CTkFont("Segoe UI", 10, "bold"),
                              corner_radius=5).grid(row=r, column=c, padx=2, pady=2)

        # ── 4-slot memory row below grid ─────────────────
        sci_mctrl = ctk.CTkFrame(card, fg_color="transparent")
        sci_mctrl.pack(padx=12, pady=(0, 4))
        ctk.CTkLabel(sci_mctrl, text="MEM:",
                     font=ctk.CTkFont("Segoe UI", 8, "bold"),
                     text_color=MUTED).pack(side="left", padx=(4, 6))
        for lbl, cmd in [("MC", self._sci_mc), ("M+", self._sci_mplus)]:
            ctk.CTkButton(sci_mctrl, text=lbl, command=cmd,
                          width=58, height=42, fg_color=INPUT_BG,
                          hover_color=INPUT_BORDER, text_color=TEXT,
                          font=ctk.CTkFont("Segoe UI", 10, "bold"),
                          corner_radius=5).pack(side="left", padx=2)
        sci_mslots = ctk.CTkFrame(card, fg_color=INPUT_BG, corner_radius=8)
        sci_mslots.pack(padx=12, pady=(0, 10), fill="x")
        for col in range(4):
            sci_mslots.columnconfigure(col, weight=1)
        for i in range(8):
            btn = ctk.CTkButton(sci_mslots, text=f"MR {i+1}\n—",
                                command=lambda s=i: self._sci_mr_slot(s),
                                width=72, height=40,
                                fg_color=CARD, hover_color=RES_BG,
                                text_color=TEXT,
                                font=ctk.CTkFont("Segoe UI", 9, "bold"),
                                corner_radius=6)
            btn.grid(row=i//4, column=i%4, padx=3, pady=4, sticky="ew")
            self._sci_mem_btns.append(btn)

    def _sci_fmt_mem(self, val):
        s = f"{val:.7g}"
        if "." in s: s = s.rstrip("0").rstrip(".")
        return s[:8] + "…" if len(s) > 8 else s

    def _sci_mem_indicator(self):
        return "".join("■" if v is not None else "□" for v in self._sci_mem_slots)

    def _sci_mc(self):
        self._sci_mem_slots = [None]*8; self._sci_next_slot = 0
        for i, b in enumerate(self._sci_mem_btns):
            b.configure(text=f"MR {i+1}\n—", fg_color=CARD)
        self._sci_mem_var.set("")

    def _sci_mplus(self):
        """Store in first empty slot; if all full, wrap to slot 0."""
        try:
            val = float(self._current)
            s = next((i for i in range(8) if self._sci_mem_slots[i] is None), 0)
            self._sci_mem_slots[s] = val
            self._sci_mem_btns[s].configure(
                text=f"MR {s+1}\n{self._sci_fmt_mem(val)}", fg_color=RES_BG)
            self._sci_mem_var.set(self._sci_mem_indicator())
            self._new_num = True
        except Exception: pass

    def _sci_mminus(self):
        try:
            val = float(self._current); s = (self._sci_next_slot - 1) % 8
            if self._sci_mem_slots[s] is not None:
                self._sci_mem_slots[s] -= val
                self._sci_mem_btns[s].configure(
                    text=f"MR {s+1}\n{self._sci_fmt_mem(self._sci_mem_slots[s])}", fg_color=RES_BG)
                self._sci_mem_var.set(self._sci_mem_indicator())
            self._new_num = True
        except Exception: pass

    def _sci_mr_slot(self, slot):
        val = self._sci_mem_slots[slot]
        if val is not None:
            fmt = self._sci_fmt_mem(val)
            self._current = str(val); self._sci_disp_var.set(fmt)
            self._new_num = True

    # ── GRAPHING PANEL ────────────────────────────────────
    def _build_graph(self, parent):
        card = make_card(parent)
        card.grid(row=0, column=1, sticky="nsew")
        card.rowconfigure(2, weight=1)
        card.columnconfigure(0, weight=1)
        section_header(card, "  GRAPHING")

        # Function entries
        fn_frame = ctk.CTkFrame(card, fg_color="transparent")
        fn_frame.pack(fill="x", padx=12, pady=(4, 2))
        self._fn_vars = []
        for i, dflt in enumerate(["sin(x)", "", "", ""]):
            row = ctk.CTkFrame(fn_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            tk.Label(row, bg=self._GCOLS[i], width=3,
                     relief="flat").pack(side="left", ipady=5, padx=(0, 6))
            ctk.CTkLabel(row, text=f"f{i+1}(x) =",
                         font=ctk.CTkFont("Segoe UI", 10, "bold"),
                         text_color=self._GCOLS[i], width=58,
                         anchor="w").pack(side="left")
            var = tk.StringVar(value=dflt)
            self._fn_vars.append(var)
            ent = ctk.CTkEntry(row, textvariable=var,
                               fg_color=INPUT_BG, border_color=INPUT_BORDER,
                               font=ctk.CTkFont("Segoe UI", 10))
            ent.pack(side="left", fill="x", expand=True)
            ent.bind("<Return>", lambda e: self._plot())

        # Range controls
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(4, 4))

        def rng(lbl, attr, val):
            ctk.CTkLabel(ctrl, text=lbl, font=ctk.CTkFont("Segoe UI", 9),
                         text_color=MUTED).pack(side="left", padx=(6, 2))
            var = tk.StringVar(value=str(val))
            setattr(self, attr, var)
            ctk.CTkEntry(ctrl, textvariable=var, width=50,
                         fg_color=INPUT_BG, border_color=INPUT_BORDER,
                         font=ctk.CTkFont("Segoe UI", 9)).pack(side="left", padx=(0, 2))

        rng("x:", "_gx_min", -10);  rng("to", "_gx_max",  10)
        rng("  y:", "_gy_min", -10); rng("to", "_gy_max",  10)

        for lbl, cmd, clr in [("▶  Plot", self._plot, ACCENT),
                               ("⟳  Reset", self._reset_view, NAV_ACT),
                               ("✕  Clear", self._clear_graph, "#888888")]:
            ctk.CTkButton(ctrl, text=lbl, command=cmd, width=84, height=28,
                          corner_radius=6, fg_color=clr, hover_color=NAV_HOV,
                          text_color="white",
                          font=ctk.CTkFont("Segoe UI", 9, "bold")).pack(
                          side="left", padx=(6, 0))

        # Hint
        ctk.CTkLabel(card,
                     text="Available: sin  cos  tan  asin  acos  atan  sinh  cosh  tanh  "
                          "log  ln  sqrt  abs  exp  floor  ceil  pi  e  "
                          "   Scroll or drag to zoom/pan",
                     font=ctk.CTkFont("Segoe UI", 8, "bold"), text_color=MUTED,
                     wraplength=500, anchor="w",
                     justify="left").pack(anchor="w", padx=12, pady=(0, 4))

        # Canvas
        self._gcanvas = tk.Canvas(card, bg="#FAFBFD",
                                  highlightthickness=1, highlightbackground=BORDER)
        self._gcanvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._gcanvas.bind("<Configure>",     self._on_graph_cfg)
        self._gcanvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._gcanvas.bind("<B1-Motion>",     self._on_drag)
        self._gcanvas.bind("<MouseWheel>",    self._on_scroll)
        self._gcanvas.bind("<Button-4>",      lambda e: self._zoom(0.85))
        self._gcanvas.bind("<Button-5>",      lambda e: self._zoom(1.15))

    # ── SCI CALC LOGIC ────────────────────────────────────
    def _sc_fmt(self, v):
        if isinstance(v, float):
            if not math.isfinite(v): return "Error"
            if v == int(v) and abs(v) < 1e15: return str(int(v))
            return f"{v:.10g}"
        return str(v)

    def _sc_set(self, v):
        self._current = self._sc_fmt(v)
        self._sci_disp_var.set(self._current)

    def _sc_num(self, d):
        if self._new_num:
            self._current = d; self._new_num = False
        else:
            if self._current == "0" and d != ".": self._current = d
            elif len(self._current.lstrip("-").replace(".", "")) < 15:
                self._current += d
        self._sci_disp_var.set(self._current)

    def _sc_dot(self):
        if self._new_num:
            self._current = "0."; self._new_num = False
        elif "." not in self._current:
            self._current += "."
        self._sci_disp_var.set(self._current)

    def _sc_back(self):
        if not self._new_num:
            self._current = self._current[:-1] or "0"
            self._sci_disp_var.set(self._current)

    def _sc_clear(self):
        self._current = "0"; self._prev = None; self._op = None
        self._new_num = True
        self._sci_disp_var.set("0"); self._sci_expr_var.set("")

    def _sc_ce(self):
        self._current = "0"; self._new_num = True; self._sci_disp_var.set("0")

    def _sc_sign(self):
        if self._current not in ("0", "Error"):
            self._current = self._current[1:] if self._current.startswith("-")                             else "-" + self._current
            self._sci_disp_var.set(self._current)

    def _sc_pct(self):
        try: self._sc_set(float(self._current) / 100)
        except: pass

    def _sc_exp(self):
        if "e" not in self._current.lower():
            self._current += "e+"; self._sci_disp_var.set(self._current)
            self._new_num = False

    def _sc_lparen(self):
        self._sci_expr_var.set(self._sci_expr_var.get() + "(")

    def _sc_rparen(self):
        self._sci_expr_var.set(self._sci_expr_var.get() + ")")

    def _sc_toggle(self):
        self._degrees = not self._degrees
        self._sci_angle_var.set("DEG" if self._degrees else "RAD")

    def _sc_op_press(self, op):
        val = float(self._current)
        if self._prev is not None and not self._new_num:
            val = self._sc_compute(self._prev, val, self._op)
            self._sc_set(val)
        self._prev = float(self._current) if self._new_num else val
        self._op = op; self._new_num = True
        self._sci_expr_var.set(f"{self._sc_fmt(self._prev)} {op}")

    def _sc_compute(self, a, b, op):
        if op == "+": return a + b
        if op == "−": return a - b
        if op == "×": return a * b
        if op == "÷": return a / b if b != 0 else float("inf")
        if op == "^": return a ** b
        return b

    def _sc_equals(self):
        if self._prev is None or self._op is None: return
        a, b, op = self._prev, float(self._current), self._op
        try:
            result = self._sc_compute(a, b, op)
        except Exception:
            self._sci_disp_var.set("Error"); self._sc_clear(); return
        self._sci_expr_var.set(f"{self._sc_fmt(a)} {op} {self._sc_fmt(b)} =")
        self._sc_set(result)
        self._prev = None; self._op = None; self._new_num = True

    def _sc_fn(self, fname):
        """Apply a unary scientific function to the current value."""
        try:
            val = float(self._current)
            d   = self._degrees
            r   = math.radians(val) if d else val

            if   fname == "sin":   res, lbl = math.sin(r),                          f"sin({self._sc_fmt(val)}{'°' if d else ''})"
            elif fname == "cos":   res, lbl = math.cos(r),                          f"cos({self._sc_fmt(val)}{'°' if d else ''})"
            elif fname == "tan":   res, lbl = math.tan(r),                          f"tan({self._sc_fmt(val)}{'°' if d else ''})"
            elif fname == "asin":  res, lbl = (math.degrees(math.asin(val)) if d else math.asin(val)), f"sin⁻¹({self._sc_fmt(val)})"
            elif fname == "acos":  res, lbl = (math.degrees(math.acos(val)) if d else math.acos(val)), f"cos⁻¹({self._sc_fmt(val)})"
            elif fname == "atan":  res, lbl = (math.degrees(math.atan(val)) if d else math.atan(val)), f"tan⁻¹({self._sc_fmt(val)})"
            elif fname == "log":   res, lbl = math.log10(val),                      f"log({self._sc_fmt(val)})"
            elif fname == "ln":    res, lbl = math.log(val),                        f"ln({self._sc_fmt(val)})"
            elif fname == "10x":   res, lbl = 10 ** val,                            f"10^{self._sc_fmt(val)}"
            elif fname == "ex":    res, lbl = math.e ** val,                        f"e^{self._sc_fmt(val)}"
            elif fname == "sq":    res, lbl = val ** 2,                             f"({self._sc_fmt(val)})²"
            elif fname == "cube":  res, lbl = val ** 3,                             f"({self._sc_fmt(val)})³"
            elif fname == "sqrt":  res, lbl = math.sqrt(val),                       f"√({self._sc_fmt(val)})"
            elif fname == "cbrt":  res, lbl = math.copysign(abs(val)**(1/3), val),  f"∛({self._sc_fmt(val)})"
            elif fname == "abs":   res, lbl = abs(val),                             f"|{self._sc_fmt(val)}|"
            elif fname == "fact":  res, lbl = float(math.factorial(int(abs(val)))), f"{self._sc_fmt(val)}!"
            elif fname == "inv":   res, lbl = 1 / val,                              f"1/({self._sc_fmt(val)})"
            elif fname == "pi":    res, lbl = math.pi,                              "π"
            elif fname == "euler": res, lbl = math.e,                               "e"
            else: return

            self._sci_expr_var.set(lbl)
            self._sc_set(res)
            self._new_num = True
        except Exception:
            self._sci_disp_var.set("Error")
            self._current = "0"; self._new_num = True

    # ── GRAPHING LOGIC ────────────────────────────────────
    def _calculate(self):
        self._plot()

    def _on_graph_cfg(self, event):
        self._gcanvas_w = event.width
        self._gcanvas_h = event.height
        self._draw_graph()

    def _plot(self):
        try:
            self._x_min = float(self._gx_min.get())
            self._x_max = float(self._gx_max.get())
            self._y_min = float(self._gy_min.get())
            self._y_max = float(self._gy_max.get())
        except Exception:
            pass
        self._draw_graph()

    def _reset_view(self):
        self._x_min = -10.0; self._x_max = 10.0
        self._y_min = -10.0; self._y_max = 10.0
        self._gx_min.set("-10"); self._gx_max.set("10")
        self._gy_min.set("-10"); self._gy_max.set("10")
        self._draw_graph()

    def _clear_graph(self):
        for v in self._fn_vars: v.set("")
        self._draw_graph()

    def _zoom(self, factor):
        cx = (self._x_min + self._x_max) / 2
        cy = (self._y_min + self._y_max) / 2
        hw = (self._x_max - self._x_min) / 2 * factor
        hh = (self._y_max - self._y_min) / 2 * factor
        self._x_min = cx - hw; self._x_max = cx + hw
        self._y_min = cy - hh; self._y_max = cy + hh
        for attr, val in [("_gx_min", self._x_min), ("_gx_max", self._x_max),
                           ("_gy_min", self._y_min), ("_gy_max", self._y_max)]:
            getattr(self, attr).set(f"{val:.3g}")
        self._draw_graph()

    def _on_scroll(self, event):
        self._zoom(0.85 if event.delta > 0 else 1.15)

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)
        self._drag_view  = (self._x_min, self._x_max, self._y_min, self._y_max)

    def _on_drag(self, event):
        if not self._drag_start or not self._drag_view: return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        W = self._gcanvas_w or 1; H = self._gcanvas_h or 1
        x0, x1, y0, y1 = self._drag_view
        self._x_min = x0 - dx / W * (x1 - x0)
        self._x_max = x1 - dx / W * (x1 - x0)
        self._y_min = y0 + dy / H * (y1 - y0)
        self._y_max = y1 + dy / H * (y1 - y0)
        self._draw_graph()

    def _draw_graph(self):
        c = self._gcanvas
        c.delete("all")
        W = self._gcanvas_w or c.winfo_width()
        H = self._gcanvas_h or c.winfo_height()
        if W < 10 or H < 10: return

        xr = self._x_max - self._x_min
        yr = self._y_max - self._y_min
        if xr == 0 or yr == 0: return

        def wx(x): return (x - self._x_min) / xr * W
        def wy(y): return H - (y - self._y_min) / yr * H

        def nice_step(span):
            raw = span / 8
            mag = 10 ** math.floor(math.log10(abs(raw) + 1e-15))
            for m in (1, 2, 5, 10):
                if m * mag >= raw: return m * mag
            return mag

        xs = nice_step(xr); ys = nice_step(yr)

        # Grid lines
        xv = math.ceil(self._x_min / xs) * xs
        while xv <= self._x_max + 1e-9:
            px = wx(xv)
            c.create_line(px, 0, px, H, fill="#E8EEF5", width=1)
            c.create_text(px, min(H - 2, wy(0) + 12),
                          text=f"{xv:.4g}" if abs(xv) > 1e-9 else "",
                          fill="#9BAAB8", font=("Segoe UI", 7), anchor="n")
            xv = round(xv + xs, 10)

        yv = math.ceil(self._y_min / ys) * ys
        while yv <= self._y_max + 1e-9:
            py = wy(yv)
            c.create_line(0, py, W, py, fill="#E8EEF5", width=1)
            c.create_text(max(2, wx(0) - 4), py,
                          text=f"{yv:.4g}" if abs(yv) > 1e-9 else "",
                          fill="#9BAAB8", font=("Segoe UI", 7), anchor="e")
            yv = round(yv + ys, 10)

        # Axes
        c.create_line(0, wy(0), W, wy(0), fill="#7A8FA6", width=1)
        c.create_line(wx(0), 0, wx(0), H, fill="#7A8FA6", width=1)

        # Plot functions
        N   = max(int(W * 2), 600)
        ns  = dict(SAFE_MATH_NS)
        for var, clr in zip(self._fn_vars, self._GCOLS):
            expr = var.get().strip()
            if not expr: continue
            pts   = []
            prev_y = None
            for i in range(N + 1):
                xi = self._x_min + i / N * xr
                try:
                    ns["x"] = xi
                    yi = float(eval(expr, {"__builtins__": {}}, ns))
                    if not math.isfinite(yi):
                        if len(pts) >= 4: c.create_line(pts, fill=clr, width=2)
                        pts = []; prev_y = None; continue
                    if prev_y is not None and abs(yi - prev_y) > yr * 3:
                        if len(pts) >= 4: c.create_line(pts, fill=clr, width=2)
                        pts = []
                    pts += [wx(xi), wy(yi)]
                    prev_y = yi
                except Exception:
                    if len(pts) >= 4: c.create_line(pts, fill=clr, width=2)
                    pts = []; prev_y = None
            if len(pts) >= 4:
                c.create_line(pts, fill=clr, width=2)



# ─────────────────────────────────────────────────────────
# TAB 9 — CONSTRUCTION CALCULATOR
# ─────────────────────────────────────────────────────────

class ConstructionCalcTab(CalcTabMixin, ctk.CTkFrame):

    # ── shape input definitions ───────────────────────────
    AREA_SHAPES = {
        "Rectangle":      [("Length (ft)", "12"), ("Width (ft)", "10")],
        "Square":         [("Side (ft)", "10")],
        "Triangle":       [("Base (ft)", "10"), ("Height (ft)", "8")],
        "Right Triangle": [("Leg A (ft)", "6"),  ("Leg B (ft)", "8")],
        "Circle":         [("Radius (ft)", "5")],
        "Trapezoid":      [("Side A (ft)", "12"), ("Side B (ft)", "8"), ("Height (ft)", "6")],
        "Ellipse":        [("Axis A (ft)", "8"),  ("Axis B (ft)", "5")],
    }
    VOL_SHAPES = {
        "Rectangular Box":  [("Length (ft)", "10"), ("Width (ft)", "8"),  ("Height (ft)", "6")],
        "Cylinder":         [("Radius (ft)", "3"),  ("Height (ft)", "8")],
        "Cone":             [("Radius (ft)", "3"),  ("Height (ft)", "8")],
        "Sphere":           [("Radius (ft)", "5")],
        "Triangular Prism": [("Base (ft)", "6"),    ("Height (ft)", "4"), ("Length (ft)", "10")],
    }
    CONC_SHAPES = {
        "Slab":          [("Length (ft)", "20"),  ("Width (ft)", "10"),  ("Thickness (in)", "4")],
        "Circular Slab": [("Diameter (ft)", "10"),("Thickness (in)", "4")],
        "Column":        [("Diameter (in)", "12"),("Height (ft)", "8"),  ("Quantity", "4")],
        "Footing":       [("Length (ft)", "10"),  ("Width (in)", "12"),  ("Depth (in)", "12"), ("Quantity", "1")],
    }

    ALL_CALCS = [
        "Master Calc",
        "Area","Batten","Concrete","Corner Angle","Crown Molding",
        "Decking","Diagonal","Frame Spacing","Lumber","Miter Joint",
        "Overlapping Boards","Parquet Floor","Ramp","Roofing",
        "Slope","Stairs","Volume",
    ]  # 18 calculators

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}   # one CTkScrollableFrame per calculator
        self._active_calc = None
        self._area_dyn   = None;  self._area_ivars  = {}
        self._vol_dyn    = None;  self._vol_ivars   = {}
        self._conc_dyn   = None;  self._conc_ivars  = {}
        self._build()

    def _calculate(self):
        name = self._active_calc
        if name == "Frame Spacing" and hasattr(self, "_fs_tab"):
            self._fs_tab._calculate(); return
        fn = {
            "Area":               self._calc_area,
            "Batten":             self._calc_batten,
            "Concrete":           self._calc_concrete,
            "Overlapping Boards": self._calc_coverboard,
            "Decking":            self._calc_decking,
            "Lumber":             self._calc_lumber,
            "Roofing":            self._calc_roofing,
            "Stairs":             self._calc_stairs,
            "Volume":             self._calc_volume,
            "Corner Angle":       self._calc_corner_angle,
            "Crown Molding":      self._calc_crown,
            "Diagonal":           self._calc_diagonal,
            "Miter Joint":        self._calc_miter,
            "Parquet Floor":      self._calc_parquet,
            "Ramp":               self._calc_ramp,
            "Slope":              self._calc_slope,
        }.get(name)
        if fn: fn()

    def show_calculator(self, name):
        """Called by App to show a specific calculator (fills full content area)."""
        for f in self._all_frames.values(): f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    # ── MAIN BUILD ────────────────────────────────────────
    def _build(self):
        # Create one CTkScrollableFrame per calculator (title inside each)
        for name in self.ALL_CALCS:
            frame = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
            if name != "Master Calc":
                ctk.CTkLabel(frame, text=name,
                         font=ctk.CTkFont("Segoe UI", 22, "bold"),
                         text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
                tk.Label(frame, text="Overwrite the sample data",
                     font=("Segoe UI", 9), fg=MUTED, bg=APP_BG,
                     anchor="w").pack(anchor="w", padx=20, pady=(0, 8))
            self._all_frames[name] = frame

        # Build all 18 calculators
        self._build_construction_master()
        self._build_area()
        self._build_batten()
        self._build_concrete()
        self._build_corner_angle()
        self._build_crown()
        self._build_decking()
        self._build_diagonal()
        self._build_framespacing()
        self._build_lumber()
        self._build_miter()
        self._build_coverboard()
        self._build_parquet()
        self._build_ramp()
        self._build_roofing()
        self._build_slope()
        self._build_stairs()
        self._build_volume()
        self._add_all_diagrams()
        self._build_cm_chart()

    # ── LAYOUT HELPERS ────────────────────────────────────
    def _le(self, parent, label, default="", width=160, on_enter=None):
        return labeled_entry(parent, label, default, width,
                             on_enter if on_enter is not None else self._calculate, fs=11)

    def _lo(self, parent, label, choices, default=None, width=160):
        return labeled_option(parent, label, choices, default, width, fs=11)

    def _le_ft(self, parent, label, default=""):
        """Labeled entry in decimal feet with live feet/inches display."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT, width=220, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(default))
        ent = ctk.CTkEntry(row, textvariable=var, width=80,
                           fg_color=INPUT_BG, border_color=INPUT_BORDER,
                           font=ctk.CTkFont("Segoe UI", 11))
        ent.pack(side="left", padx=(8, 0))
        disp = tk.StringVar(value="")
        ctk.CTkLabel(row, textvariable=disp, font=ctk.CTkFont("Segoe UI", 11),
                     text_color=ACCENT, width=110, anchor="w").pack(side="left", padx=(10,0))
        def _upd(*_):
            try: disp.set(inches_to_feet(float(var.get())*12))
            except: disp.set("")
        var.trace_add("write", _upd); _upd()
        ent.bind("<Return>", lambda e: self._calculate())
        return var

    def _two_col(self, parent):
        """Return (input_inner, results_frame)."""
        cols = ctk.CTkFrame(parent, fg_color="transparent")
        cols.pack(fill="x", padx=10, pady=10)
        cols.columnconfigure(0, weight=1); cols.columnconfigure(1, weight=1)
        cols.rowconfigure(0, weight=1)
        cl = make_card(cols); cl.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cr = make_card(cols); cr.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        section_header(cl, "  INPUTS"); section_header(cr, "  RESULTS")
        inner = ctk.CTkFrame(cl, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 12))
        res = ctk.CTkFrame(cr, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        return inner, res

    @staticmethod
    def _g(d, k, default=0.0):
        """Safe float get from StringVar dict."""
        try: return float(d.get(k, tk.StringVar(value=str(default))).get().replace(",",""))
        except: return default

    def _refresh_dyn(self, container, shape_var, shapes_map, ivar_attr):
        """Rebuild dynamic inputs when shape changes."""
        for w in container.winfo_children(): w.destroy()
        d = {}
        for lbl, dflt in shapes_map.get(shape_var.get(), []):
            d[lbl] = labeled_entry(container, lbl, dflt,
                                   on_enter=self._calculate, fs=11)
        setattr(self, ivar_attr, d)

    def _rr(self, res, lbl, var, color=None):
        result_row(res, lbl, var, color=color or TEXT, lbl_fs=11, val_fs=12, row_h=36)

    # ── FRAME SPACING (embedded) ─────────────────────────
    def _build_framespacing(self):
        tab = self._all_frames["Frame Spacing"]
        self._fs_tab = FrameSpacingTab(tab)
        self._fs_tab.pack(fill="both", expand=True)

    # ── AREA ──────────────────────────────────────────────

    # ── CONSTRUCTION MASTER ──────────────────────────────────────────────────
    def _build_construction_master(self):
        from fractions import Fraction as _Frac
        import math as _math
        frame = self._all_frames["Master Calc"]
        INCH = chr(34); FOOT = chr(39)
        s = {'inp':'0','val':0.0,'prev':None,'op':None,'fresh':True,
             'unit':None,'expr':'','pitch':None,'rise':None,
             'run':None,'diag':None,'mem':[None]*8,'dec':True}
        TO_FT   = {'yds':3.0,'feet':1.0,'inch':1/12.0,'m':3.28084,'cm':0.0328084,'mm':0.00328084}
        FROM_FT = {'yds':1/3.0,'feet':1.0,'inch':12.0,'m':0.3048,'cm':30.48,'mm':304.8}
        ULBL    = {'yds':' yd','feet':' ft','inch':' in','m':' m','cm':' cm','mm':' mm'}
        METRIC  = {'m','cm','mm'}
        dec_ref = [None]

        def parse_inp(txt):
            txt=txt.strip()
            if not txt or txt=='0': return 0.0
            try:
                if '/' in txt:
                    si=txt.index('/'); np_s=txt[:si]; ds=txt[si+1:]
                    denom=float(ds) if ds else 1.0
                    if denom==0: denom=1.0
                    if '.' in np_s:
                        di=np_s.index('.')
                        whole=float(np_s[:di]) if np_s[:di] else 0.0
                        fnum=float(np_s[di+1:]) if np_s[di+1:] else 0.0
                    else: whole=0.0; fnum=float(np_s) if np_s else 0.0
                    return whole+fnum/denom
                return float(txt)
            except Exception: return 0.0

        def fmt_frac(v):
            if abs(v)<1e-10: return '0'
            try:
                f=_Frac(v).limit_denominator(10000)
                sign='-' if f<0 else ''
                n=abs(f.numerator); d=f.denominator
                if d==1: return sign+str(n)
                whole=n//d; rem=n%d
                if whole==0: return sign+str(rem)+'/'+str(d)
                return sign+str(whole)+' '+str(rem)+'/'+str(d)
            except Exception: return f"{v:.6g}"

        def fmt_disp(val_ft, unit):
            scale=FROM_FT.get(unit,1.0) if unit else 1.0
            v=val_ft*scale if unit else val_ft
            lbl=ULBL.get(unit,'')
            if s['dec'] or unit in METRIC: return f"{v:.6g}"+lbl
            return fmt_frac(v)+lbl

        def upd():
            if s['fresh'] or s['inp'] in ('0',''):
                dvar.set(fmt_disp(s['val'],s['unit']))
                mode='  [DEC]' if s['dec'] else '  [FRAC]'
                evar.set((s['expr'] if s['expr'] else chr(0x2015))+mode)
            else:
                evar.set(s['inp']+('  [DEC]' if s['dec'] else '  [FRAC]'))
                dvar.set(s['inp'])

        def _ref_dec():
            b=dec_ref[0]
            if not b: return
            if s['dec']: b.configure(fg_color=ACCENT,text_color='white',text='Dec/Frac')
            else: b.configure(fg_color=NAV_BG,text_color='white',text='Frac')

        def toggle_dec(): s['dec']=not s['dec']; _ref_dec(); upd()

        def dgt(d):
            if s['fresh']: s['inp']=d; s['fresh']=False
            elif s['inp']=='0' and d!='.': s['inp']=d
            else: s['inp']+=d
            upd()
        def dot():
            if s['fresh']: s['inp']='0.'; s['fresh']=False
            elif '.' not in s['inp']: s['inp']+='.' 
            upd()
        def sfrac():
            if s['dec']: s['dec']=False; _ref_dec()
            if s['fresh']: s['inp']='0/'; s['fresh']=False
            elif '/' not in s['inp']: s['inp']+='/'
            upd()
        def bksp():
            if s['fresh'] or s['inp'] in ('0',''):
                s['val']=0.0; s['fresh']=True; s['inp']='0'
            else: s['inp']=s['inp'][:-1] or '0'
            upd()
        def ac():
            s.update({'inp':'0','val':0.0,'prev':None,'op':None,'fresh':True,
                       'expr':'','pitch':None,'rise':None,'run':None,'diag':None}); upd()
        def ce(): s['inp']='0'; s['fresh']=False; upd()

        def _cur():
            if not s['fresh'] and s['inp'] not in ('0',''):
                return parse_inp(s['inp'])*TO_FT.get(s['unit'] or 'feet',1.0)
            return s['val']
        def _raw():
            if not s['fresh'] and s['inp'] not in ('0',''): return parse_inp(s['inp'])
            return s['val']
        def _ap(a,b,o):
            if o=='+': return a+b
            if o=='-': return a-b
            if o=='x': return a*b
            if o=='/': return a/b if b else 0.0
            return b
        DIV=chr(0x00F7); MUL=chr(0x00D7); MIN=chr(0x2212)
        OSYM={'+':'+','-':MIN,'x':MUL,'/':DIV}

        def op_p(o):
            v=_raw() if s['unit'] is None else _cur()
            s['val']=v; s['prev']=v; s['op']=o; s['inp']='0'; s['fresh']=True
            s['expr']=fmt_disp(v,s['unit'])+' '+OSYM.get(o,o); upd()

        def eq():
            v=_raw() if s['unit'] is None else _cur()
            if s['op'] and s['prev'] is not None:
                s['expr']=(fmt_disp(s['prev'],s['unit'])+' '+OSYM.get(s['op'],s['op'])+
                           ' '+fmt_disp(v,s['unit'])+' =')
                s['val']=_ap(s['prev'],v,s['op']); s['prev']=None; s['op']=None
            else: s['val']=v; s['expr']=fmt_disp(v,s['unit'])
            s['inp']='0'; s['fresh']=True; upd()

        def unit_p(u):
            s['unit']=u
            if not s['fresh'] and s['inp'] not in ('0',''):
                raw=parse_inp(s['inp']); v_ft=raw*TO_FT.get(u,1.0)
                if s['op'] and s['prev'] is not None:
                    s['expr']=(fmt_disp(s['prev'],u)+' '+OSYM.get(s['op'],s['op'])+
                               ' '+fmt_disp(v_ft,u)+' =')
                    s['val']=_ap(s['prev'],v_ft,s['op']); s['prev']=None; s['op']=None
                else: s['val']=v_ft; s['expr']=fmt_disp(v_ft,u)
                s['inp']='0'; s['fresh']=True
            upd()

        def prd(pt):
            if not s['fresh'] and s['inp'] not in ('0',''):
                v_ft=parse_inp(s['inp'])*TO_FT.get(s['unit'] or 'feet',1.0)
                s[pt]=v_ft; s['expr']=pt.capitalize()+' = '+fmt_disp(v_ft,s['unit'])
                s['val']=v_ft; s['inp']='0'; s['fresh']=True; upd(); return
            p=s.get('pitch'); ri=s.get('rise'); ru=s.get('run'); di=s.get('diag')
            try:
                if pt=='pitch' and ri is not None and ru and ru!=0:
                    pv=(ri/ru)*12; s['pitch']=pv; s['val']=pv
                    s['expr']='Pitch = '+fmt_disp(pv,None)
                elif pt=='rise':
                    rv=(ru*(p/12) if p is not None and ru is not None else
                        _math.sqrt(max(0,di*di-ru*ru)) if di is not None and ru is not None else None)
                    if rv is not None: s['rise']=rv; s['val']=rv; s['expr']='Rise = '+fmt_disp(rv,s['unit'])
                elif pt=='run':
                    rv=(ri/(p/12) if p is not None and ri is not None and p!=0 else
                        _math.sqrt(max(0,di*di-ri*ri)) if di is not None and ri is not None else None)
                    if rv is not None: s['run']=rv; s['val']=rv; s['expr']='Run = '+fmt_disp(rv,s['unit'])
                elif pt=='diag':
                    dv=(_math.sqrt(ri*ri+ru*ru) if ri is not None and ru is not None else
                        _math.sqrt((ru*(p/12))**2+ru*ru) if p is not None and ru is not None else None)
                    if dv is not None: s['diag']=dv; s['val']=dv; s['expr']='Diag = '+fmt_disp(dv,s['unit'])
            except Exception: pass
            s['inp']='0'; s['fresh']=True; upd()

        def m_lbl(i):
            v=s['mem'][i]
            return 'MR '+str(i+1)+chr(10)+(chr(0x2014) if v is None else fmt_disp(v,s['unit'])[:9])
        def m_rcl(i):
            s['val']=s['mem'][i]; s['fresh']=True; s['inp']='0'
            mem_btns[i].configure(text=m_lbl(i)); upd()
        def m_sto(i):
            v=_raw() if s['unit'] is None else _cur()
            s['mem'][i]=v
            mem_btns[i].configure(text=m_lbl(i),fg_color=RES_BG)
        def mc():
            s['mem']=[None]*8
            for i,b in enumerate(mem_btns): b.configure(text='MR '+str(i+1)+chr(10)+chr(0x2014),fg_color=CARD)
        def ms():  # M+ — store to first empty slot
            for i in range(8):
                if s['mem'][i] is None: m_sto(i); return
            m_sto(0)
        def mplus():
            v=_raw() if s['unit'] is None else _cur()
            for i in range(7,-1,-1):
                if s['mem'][i]!=0.0: s['mem'][i]+=v; mem_btns[i].configure(text=m_lbl(i)); return
            s['mem'][0]+=v; mem_btns[0].configure(text=m_lbl(0))
        def mmin():
            v=_raw() if s['unit'] is None else _cur()
            for i in range(7,-1,-1):
                if s['mem'][i]!=0.0: s['mem'][i]-=v; mem_btns[i].configure(text=m_lbl(i)); return
        def pneg():
            if not s['fresh']: s['inp']=s['inp'][1:] if s['inp'].startswith('-') else '-'+s['inp']
            else: s['val']=-s['val']
            upd()

        def on_key(event):
            try:
                if not frame.winfo_ismapped(): return
            except Exception: return
            k=event.keysym
            if k in ('Return','KP_Enter'): eq()
            elif k=='BackSpace': bksp()
            elif k=='Escape': ac()
            elif k=='Delete': ce()
            elif k in ('plus','KP_Add'): op_p('+')
            elif k in ('minus','KP_Subtract'): op_p('-')
            elif k in ('asterisk','KP_Multiply'): op_p('x')
            elif k in ('slash','KP_Divide'): sfrac()
            elif k in ('period','comma','KP_Decimal'): dot()
            elif k.isdigit(): dgt(k)
            elif k.startswith('KP_') and k[3:].isdigit(): dgt(k[3:])
        frame.bind_all('<Key>', on_key)

        WC=80; WN=78; H=48; FS=13
        main=ctk.CTkFrame(frame,fg_color='transparent')
        main.pack(fill='both',expand=True,padx=8,pady=(4,6))
        body=ctk.CTkFrame(main,fg_color='transparent')
        body.pack(fill='both',expand=True)
        mp=ctk.CTkFrame(body,fg_color=CARD,corner_radius=8,border_width=1,border_color=BORDER)
        mp.pack(side='left',fill='y',padx=(0,6))
        ctk.CTkLabel(mp,text='MEMORY',font=ctk.CTkFont('Segoe UI',9,'bold'),text_color=MUTED).pack(pady=(6,2))
        mem_btns=[]
        for i in range(8):
            b=ctk.CTkButton(mp,text='MR '+str(i+1)+chr(10)+chr(0x2014),width=80,height=48,
                             font=ctk.CTkFont('Segoe UI',10),fg_color=CARD,hover_color=RES_BG,
                             text_color=TEXT,border_width=1,border_color=BORDER,
                             command=lambda idx=i: m_rcl(idx))
            b.pack(pady=2,padx=4); b.bind('<Button-3>',lambda e,idx=i: m_sto(idx)); mem_btns.append(b)
        rp=ctk.CTkFrame(body,fg_color='transparent'); rp.pack(side='left',fill='both',expand=True)
        dsp=ctk.CTkFrame(rp,fg_color=NAV_BG,corner_radius=8); dsp.pack(fill='x',pady=(0,6))
        evar=tk.StringVar(value=chr(0x2015)+'  [DEC]'); dvar=tk.StringVar(value='0')
        tk.Label(dsp,textvariable=evar,font=('Segoe UI',10),fg='#90C8F0',bg=NAV_BG,anchor='e',
                 justify='right').pack(fill='x',padx=12,pady=(7,0))
        tk.Label(dsp,textvariable=dvar,font=('Segoe UI',24,'bold'),fg='white',bg=NAV_BG,anchor='e',
                 justify='right').pack(fill='x',padx=12,pady=(2,9))
        def row():
            r=ctk.CTkFrame(rp,fg_color='transparent'); r.pack(fill='x',pady=1); return r
        def mkb(par,lbl,cmd,bg,fg='white',w=None,h=H,fs=FS):
            b=ctk.CTkButton(par,text=lbl,width=w or WC,height=h,fg_color=bg,hover_color=NAV_HOV,
                             text_color=fg,font=ctk.CTkFont('Segoe UI',fs,'bold'),command=cmd)
            b.pack(side='left',padx=2,pady=1); return b
        r=row()
        for lbl,pt in [('Pitch','pitch'),('Rise','rise'),('Run','run'),('Diag','diag')]:
            mkb(r,lbl,lambda p=pt:prd(p),bg=ACCENT)
        r=row()
        mkb(r,'Yds',lambda:unit_p('yds'),bg=NAV_BG)
        mkb(r,'Feet',lambda:unit_p('feet'),bg=NAV_BG)
        mkb(r,'Inch',lambda:unit_p('inch'),bg=NAV_BG)
        mkb(r,'/',sfrac,bg=NAV_BG,fs=FS+2)
        r=row()
        mkb(r,'m',lambda:unit_p('m'),bg=NAV_BG)
        mkb(r,'cm',lambda:unit_p('cm'),bg=NAV_BG)
        mkb(r,'mm',lambda:unit_p('mm'),bg=NAV_BG)
        mkb(r,chr(0x2190),bksp,bg=NAV_BG,fs=FS+3)
        ctk.CTkFrame(rp,fg_color=BORDER,height=1).pack(fill='x',pady=3)
        r=row()
        for lbl,cmd in [('MC',mc),('M+',ms)]:
            mkb(r,lbl,cmd,bg=CARD,fg=TEXT,w=WC)
        mkb(r,'Dec/Frac',toggle_dec,bg=ACCENT,fg='white',w=WC)
        OPS={DIV,MUL,MIN,'+'}
        NROWS=[
            [('7',lambda:dgt('7')),('8',lambda:dgt('8')),('9',lambda:dgt('9')),(DIV,lambda:op_p('/'))],
            [('4',lambda:dgt('4')),('5',lambda:dgt('5')),('6',lambda:dgt('6')),(MUL,lambda:op_p('x'))],
            [('1',lambda:dgt('1')),('2',lambda:dgt('2')),('3',lambda:dgt('3')),(MIN,lambda:op_p('-'))],
            [('+/'+MIN,pneg),('0',lambda:dgt('0')),('.',dot),('+',lambda:op_p('+'))],
            [('AC',ac),('CE',ce),('=',eq)],
        ]
        for nr in NROWS:
            r=row()
            for lbl,cmd in nr:
                bg=(ACCENT if lbl=='=' else NAV_ACT if lbl in OPS else
                    ACCENT if lbl=='Dec' else BTN_SECONDARY if lbl in {'AC','CE','+/'+MIN} else INPUT_BG)
                fg='white' if lbl in OPS|{'=','Dec'} else TEXT
                b=mkb(r,lbl,cmd,bg=bg,fg=fg,w=WN)
                if lbl=='Dec': dec_ref[0]=b


    def _build_area(self):
        inner, res = self._two_col(self._all_frames["Area"])
        self._area_shape = self._lo(inner, "Shape",
            list(self.AREA_SHAPES), "Rectangle")
        self._area_dyn = ctk.CTkFrame(inner, fg_color="transparent")
        self._area_dyn.pack(fill="x")
        calc_button(inner, "Calculate →", self._calc_area, clear_cmd=self._clear_area, sample_cmd=self._sample_area)
        def _refresh(*_): self._refresh_dyn(self._area_dyn, self._area_shape,
                                             self.AREA_SHAPES, "_area_ivars")
        self._area_shape.trace_add("write", _refresh); _refresh()

        self._a_sqft = tk.StringVar(value="—"); self._a_sqin = tk.StringVar(value="—")
        self._a_sqyd = tk.StringVar(value="—"); self._a_sqm  = tk.StringVar(value="—")
        self._a_perim= tk.StringVar(value="—")
        self._rr(res, "Area (sq ft)",    self._a_sqft, ACCENT)
        self._rr(res, "Area (sq in)",    self._a_sqin)
        self._rr(res, "Area (sq yards)", self._a_sqyd)
        self._rr(res, "Area (sq m)",     self._a_sqm)
        self._rr(res, "Perimeter / Circumference (ft)", self._a_perim)

    def _calc_area(self):
        g = lambda k, d=0: self._g(self._area_ivars, k, d)
        shape = self._area_shape.get()
        try:
            if shape == "Rectangle":
                a = g("Length (ft)") * g("Width (ft)")
                p = 2 * (g("Length (ft)") + g("Width (ft)"))
            elif shape == "Square":
                a = g("Side (ft)") ** 2
                p = 4 * g("Side (ft)")
            elif shape == "Triangle":
                a = 0.5 * g("Base (ft)") * g("Height (ft)")
                p = None
            elif shape == "Right Triangle":
                la, lb = g("Leg A (ft)"), g("Leg B (ft)")
                a = 0.5 * la * lb
                c = math.sqrt(la**2 + lb**2)
                p = la + lb + c
            elif shape == "Circle":
                r = g("Radius (ft)")
                a = math.pi * r**2
                p = 2 * math.pi * r
            elif shape == "Trapezoid":
                a = 0.5 * (g("Side A (ft)") + g("Side B (ft)")) * g("Height (ft)")
                p = None
            elif shape == "Ellipse":
                ea, eb = g("Axis A (ft)"), g("Axis B (ft)")
                a = math.pi * ea * eb
                hh = ((ea - eb) / (ea + eb)) ** 2
                p = math.pi * (ea + eb) * (1 + 3*hh / (10 + math.sqrt(4 - 3*hh)))
            else:
                return
            self._a_sqft.set(f"{a:,.4f}");        self._a_sqin.set(f"{a*144:,.2f}")
            self._a_sqyd.set(f"{a/9:,.4f}");      self._a_sqm.set(f"{a*0.092903:,.4f}")
            self._a_perim.set(f"{p:,.3f}" if p else "—")
            g2 = lambda k,d=0: self._g(self._area_ivars, k, d)
            self._area_diag = dict(shape=shape,
                w=g2("Length (ft)"), h=g2("Width (ft)"), s=g2("Side (ft)"),
                b=g2("Base (ft)"), ht=g2("Height (ft)"),
                la=g2("Leg A (ft)"), lb=g2("Leg B (ft)"),
                hyp=math.sqrt(g2("Leg A (ft)")**2+g2("Leg B (ft)")**2) if shape=="Right Triangle" else 0,
                r=g2("Radius (ft)"), sa=g2("Side A (ft)"), sb=g2("Side B (ft)"),
                ea=g2("Axis A (ft)"), eb=g2("Axis B (ft)"))
            self._draw_area_diagram()
        except Exception as e: self._a_sqft.set(f"Error: {e}")

    # ── VOLUME ────────────────────────────────────────────
    def _build_volume(self):
        inner, res = self._two_col(self._all_frames["Volume"])
        self._vol_shape = self._lo(inner, "Shape",
            list(self.VOL_SHAPES), "Rectangular Box")
        self._vol_dyn = ctk.CTkFrame(inner, fg_color="transparent")
        self._vol_dyn.pack(fill="x")
        calc_button(inner, "Calculate →", self._calc_volume, clear_cmd=self._clear_volume, sample_cmd=self._sample_volume)
        def _refresh(*_): self._refresh_dyn(self._vol_dyn, self._vol_shape,
                                             self.VOL_SHAPES, "_vol_ivars")
        self._vol_shape.trace_add("write", _refresh); _refresh()

        self._v_cuft=tk.StringVar(value="—"); self._v_cuin=tk.StringVar(value="—")
        self._v_cuyd=tk.StringVar(value="—"); self._v_cum =tk.StringVar(value="—")
        self._v_gal =tk.StringVar(value="—"); self._v_sa  =tk.StringVar(value="—")
        self._rr(res, "Volume (cu ft)",     self._v_cuft, ACCENT)
        self._rr(res, "Volume (cu in)",     self._v_cuin)
        self._rr(res, "Volume (cu yards)",  self._v_cuyd)
        self._rr(res, "Volume (cu m)",      self._v_cum)
        self._rr(res, "Volume (gallons)",   self._v_gal)
        self._rr(res, "Surface Area (sq ft)", self._v_sa)

    def _calc_volume(self):
        g = lambda k, d=0: self._g(self._vol_ivars, k, d)
        shape = self._vol_shape.get()
        try:
            sa = None
            if   shape == "Rectangular Box":
                l,w,h = g("Length (ft)"),g("Width (ft)"),g("Height (ft)")
                v = l*w*h; sa = 2*(l*w+l*h+w*h)
            elif shape == "Cylinder":
                r,h = g("Radius (ft)"),g("Height (ft)")
                v = math.pi*r**2*h; sa = 2*math.pi*r*(r+h)
            elif shape == "Cone":
                r,h = g("Radius (ft)"),g("Height (ft)")
                sl = math.sqrt(r**2+h**2)
                v = (1/3)*math.pi*r**2*h; sa = math.pi*r*(r+sl)
            elif shape == "Sphere":
                r = g("Radius (ft)"); v = (4/3)*math.pi*r**3; sa = 4*math.pi*r**2
            elif shape == "Triangular Prism":
                b,h,l = g("Base (ft)"),g("Height (ft)"),g("Length (ft)")
                v = 0.5*b*h*l; sa = None
            else: return
            self._v_cuft.set(f"{v:,.4f}");      self._v_cuin.set(f"{v*1728:,.2f}")
            self._v_cuyd.set(f"{v/27:,.4f}");   self._v_cum.set(f"{v*0.0283168:,.4f}")
            self._v_gal.set(f"{v*7.48052:,.3f}")
            self._v_sa.set(f"{sa:,.3f}" if sa else "—")
            gv = lambda k,d=0: self._g(self._vol_ivars, k, d)
            sl_v = math.sqrt(gv("Radius (ft)")**2+gv("Height (ft)")**2) if shape=="Cone" else 0
            self._vol_diag = dict(shape=shape,
                L=gv("Length (ft)"), W=gv("Width (ft)"), H=gv("Height (ft)"),
                r=gv("Radius (ft)"), h=gv("Height (ft)"), sl=sl_v,
                b=gv("Base (ft)"), l=gv("Length (ft)"))
            self._draw_vol_diagram()
        except Exception as e: self._v_cuft.set(f"Error: {e}")

    # ── STAIRS ────────────────────────────────────────────
    def _build_stairs(self):
        inner, res = self._two_col(self._all_frames["Stairs"])
        self._st_rise  = self._le(inner, "Total Rise — floor to floor (in)", "108")
        self._st_des_r = self._le(inner, "Desired Rise per Step (in)",       "7.0")
        self._st_tread = self._le(inner, "Tread Depth — board width (in)",   "11.25")
        self._st_nose  = self._le(inner, "Nosing Overhang (in)",             "0.75")
        calc_button(inner, "Calculate →", self._calc_stairs, clear_cmd=self._clear_stairs, sample_cmd=self._sample_stairs)

        self._st_nris=tk.StringVar(value="—"); self._st_arise=tk.StringVar(value="—")
        self._st_ntrd=tk.StringVar(value="—"); self._st_trun =tk.StringVar(value="—")
        self._st_trun_ft=tk.StringVar(value="—"); self._st_slen=tk.StringVar(value="—")
        self._st_ang=tk.StringVar(value="—"); self._st_ang2=tk.StringVar(value="—")
        self._st_code=tk.StringVar(value="—")
        self._rr(res, "Number of Risers",          self._st_nris,    ACCENT)
        self._rr(res, "Actual Rise per Step (in)",  self._st_arise)
        self._rr(res, "Number of Treads",           self._st_ntrd)
        self._rr(res, "Total Horizontal Run (in)",  self._st_trun)
        self._rr(res, "Total Horizontal Run (ft)",  self._st_trun_ft)
        self._rr(res, "Stringer Length (ft)",       self._st_slen)
        self._st_nose_v = tk.StringVar(value="—")
        self._rr(res, "Nosing Overhang (in)",        self._st_nose_v)
        self._rr(res, "Effective Run (in)",          self._st_ang)
        self._rr(res, "Stair Angle (°)",             self._st_ang2)
        self._rr(res, "Code Check  2R+T",            self._st_code)

    def _calc_stairs(self):
        try:
            total  = float(self._st_rise.get())
            des_r  = float(self._st_des_r.get())
            tread  = float(self._st_tread.get())   # board width incl. nosing
            nose   = float(self._st_nose.get())    # nosing overhang
            run    = tread - nose                   # effective horizontal run per step
            n_ris  = math.ceil(total / des_r)
            act_r  = total / n_ris
            n_trd  = n_ris - 1
            t_run  = n_trd * run
            s_len  = math.sqrt(total**2 + t_run**2) / 12
            angle  = math.degrees(math.atan(total / t_run)) if t_run else 90
            rule   = 2*act_r + run                  # code check uses run, not tread
            ok     = "✓  OK" if 24 <= rule <= 25 else f"⚠  {rule:.2f}\" (ideal 24-25\")"
            self._st_nris.set(str(n_ris));             self._st_arise.set(f"{act_r:.4f}\"")
            self._st_ntrd.set(str(n_trd));             self._st_trun.set(f"{t_run:.3f}\"")
            self._st_trun_ft.set(f"{t_run/12:.3f} ft"); self._st_slen.set(f"{s_len:.3f} ft")
            self._st_nose_v.set(f"{nose:.3f}\"")
            self._st_ang.set(f"{run:.3f}\"")
            self._st_ang2.set(f"{angle:.2f}°")
            self._st_code.set(ok)
            self._st_diag = dict(n_ris=n_ris,act_r=act_r,tread=tread,run=run,
                                  nose=nose,t_run=t_run,total=total)
            self._draw_st_diagram()
        except Exception as e: self._st_nris.set(f"Error: {e}")

    # ── CONCRETE ──────────────────────────────────────────
    def _build_concrete(self):
        inner, res = self._two_col(self._all_frames["Concrete"])
        self._conc_shape = self._lo(inner, "Shape",
            list(self.CONC_SHAPES), "Slab")
        self._conc_dyn = ctk.CTkFrame(inner, fg_color="transparent")
        self._conc_dyn.pack(fill="x")
        self._cn_waste = self._le(inner, "Waste Factor (%)", "10")
        calc_button(inner, "Calculate →", self._calc_concrete, clear_cmd=self._clear_concrete, sample_cmd=self._sample_concrete)
        def _refresh(*_): self._refresh_dyn(self._conc_dyn, self._conc_shape,
                                             self.CONC_SHAPES, "_conc_ivars")
        self._conc_shape.trace_add("write", _refresh); _refresh()

        self._cn_cuft = tk.StringVar(value="—"); self._cn_cuyd = tk.StringVar(value="—")
        self._cn_cuftw= tk.StringVar(value="—"); self._cn_cuydw= tk.StringVar(value="—")
        self._cn_b60  = tk.StringVar(value="—"); self._cn_b80  = tk.StringVar(value="—")
        self._rr(res, "Volume (cubic feet)",            self._cn_cuft,  ACCENT)
        self._rr(res, "Volume (cubic yards)",           self._cn_cuyd)
        self._rr(res, "Volume with Waste (cubic feet)", self._cn_cuftw)
        self._rr(res, "Volume with Waste (cubic yards)",self._cn_cuydw)
        self._rr(res, "60 lb bags needed (with waste)", self._cn_b60)
        self._rr(res, "80 lb bags needed (with waste)", self._cn_b80)
        ctk.CTkLabel(res, text="1 cu yd = 27 cu ft.",
                     font=ctk.CTkFont("Segoe UI", 9, "bold"), text_color=MUTED
                     ).pack(anchor="w", pady=(6, 0))

    def _calc_concrete(self):
        g = lambda k, d=0: self._g(self._conc_ivars, k, d)
        shape = self._conc_shape.get()
        try:
            if   shape == "Slab":
                v = g("Length (ft)") * g("Width (ft)") * (g("Thickness (in)") / 12)
            elif shape == "Circular Slab":
                r = g("Diameter (ft)") / 2
                v = math.pi * r**2 * (g("Thickness (in)") / 12)
            elif shape == "Column":
                r = (g("Diameter (in)") / 12) / 2
                v = math.pi * r**2 * g("Height (ft)") * g("Quantity")
            elif shape == "Footing":
                v = g("Length (ft)") * (g("Width (in)")/12) * (g("Depth (in)")/12) * g("Quantity")
            else: return
            waste = float(self._cn_waste.get()) / 100
            vw = v * (1 + waste)
            cy = v / 27;  cyw = vw / 27
            self._cn_cuft.set(f"{v:,.3f}");   self._cn_cuyd.set(f"{cy:,.3f}")
            self._cn_cuftw.set(f"{vw:,.3f}"); self._cn_cuydw.set(f"{cyw:,.3f}")
            self._cn_b60.set(f"{math.ceil(vw/0.45)} bags")
            self._cn_b80.set(f"{math.ceil(vw/0.60)} bags")
            gc = lambda k,d=0: self._g(self._conc_ivars, k, d)
            self._cn_diag = dict(shape=shape,
                L=gc("Length (ft)"), W=gc("Width (ft)"), T=gc("Thickness (in)"),
                D=gc("Diameter (ft)"), H=gc("Height (ft)"),
                Wi=gc("Width (in)"), Dp=gc("Depth (in)"))
            self._draw_cn_diagram()
        except Exception as e: self._cn_cuft.set(f"Error: {e}")

    # ── ROOFING ───────────────────────────────────────────
    def _build_roofing(self):
        inner, res = self._two_col(self._all_frames["Roofing"])
        self._rf_len   = self._le(inner, "Building Length (ft)", "40")
        self._rf_wid   = self._le(inner, "Building Width (ft)",  "30")
        self._rf_pitch = self._le(inner, "Roof Pitch (X : 12)",  "6")
        self._rf_waste = self._le(inner, "Waste Factor (%)",      "10")
        calc_button(inner, "Calculate →", self._calc_roofing, clear_cmd=self._clear_roofing, sample_cmd=self._sample_roofing)

        self._rf_flat =tk.StringVar(value="—"); self._rf_act  =tk.StringVar(value="—")
        self._rf_sq   =tk.StringVar(value="—"); self._rf_sqw  =tk.StringVar(value="—")
        self._rf_raft =tk.StringVar(value="—"); self._rf_ridge=tk.StringVar(value="—")
        self._rf_ang  =tk.StringVar(value="—")
        self._rr(res, "Flat Ceiling Area (sq ft)",       self._rf_flat)
        self._rr(res, "Actual Roof Area (sq ft)",        self._rf_act,  ACCENT)
        self._rr(res, "Roofing Squares (100 sq ft)",     self._rf_sq)
        self._rr(res, "Squares with Waste",              self._rf_sqw)
        self._rr(res, "Rafter Length (ft)",              self._rf_raft)
        self._rr(res, "Ridge Length (ft)",               self._rf_ridge)
        self._rr(res, "Roof Angle (°)",                  self._rf_ang)

    def _calc_roofing(self):
        try:
            L = float(self._rf_len.get()); W = float(self._rf_wid.get())
            pitch = float(self._rf_pitch.get()); waste = float(self._rf_waste.get())/100
            slope = math.sqrt(1 + (pitch/12)**2)
            flat  = L * W
            act   = flat * slope
            sq    = act / 100
            sqw   = sq * (1 + waste)
            half  = W / 2
            raft  = math.sqrt(half**2 + (half * pitch/12)**2)
            ang   = math.degrees(math.atan(pitch / 12))
            self._rf_flat.set(f"{flat:,.2f}");   self._rf_act.set(f"{act:,.2f}")
            self._rf_sq.set(f"{sq:,.2f}");       self._rf_sqw.set(f"{sqw:,.2f}")
            self._rf_raft.set(f"{raft:,.3f}");   self._rf_ridge.set(f"{L:,.2f}")
            self._rf_ang.set(f"{ang:,.2f}°")
            self._rf_diag = dict(W=W, L=L, pitch=pitch, raft=raft, ang=ang)
            self._draw_rf_diagram()
        except Exception as e: self._rf_flat.set(f"Error: {e}")

    # ── LUMBER ────────────────────────────────────────────
    def _build_lumber(self):
        inner, res = self._two_col(self._all_frames["Lumber"])
        self._lb_thick = self._le(inner, "Thickness (in)",   "1.5")
        self._lb_width = self._le(inner, "Width (in)",       "3.5")
        self._lb_len   = self._le(inner, "Length (ft)",      "8")
        self._lb_qty   = self._le(inner, "Quantity (pieces)","10")
        self._lb_waste = self._le(inner, "Waste Factor (%)", "10")
        self._lb_price = self._le(inner, "Price per BF ($)", "0")
        calc_button(inner, "Calculate →", self._calc_lumber, clear_cmd=self._clear_lumber, sample_cmd=self._sample_lumber)

        self._lm_bfpc =tk.StringVar(value="—"); self._lm_totbf=tk.StringVar(value="—")
        self._lm_wastbf=tk.StringVar(value="—");self._lm_cost =tk.StringVar(value="—")
        self._lm_linft =tk.StringVar(value="—"); self._lm_note=tk.StringVar(value="—")
        self._rr(res, "Board Feet per Piece",        self._lm_bfpc,   ACCENT)
        self._rr(res, "Total Board Feet",            self._lm_totbf)
        self._rr(res, "Board Feet with Waste",       self._lm_wastbf)
        self._rr(res, "Estimated Cost ($)",          self._lm_cost)
        self._rr(res, "Total Linear Feet",           self._lm_linft)
        ctk.CTkLabel(res, text='1 board foot = 1" x 12" x 12"',
                     font=ctk.CTkFont("Segoe UI", 9, "bold"), text_color=MUTED
                     ).pack(anchor="w", pady=(6, 0))

    def _calc_lumber(self):
        try:
            t   = float(self._lb_thick.get()); w = float(self._lb_width.get())
            l   = float(self._lb_len.get());   q = float(self._lb_qty.get())
            wst = float(self._lb_waste.get())/100
            prc = float(self._lb_price.get())
            bf_pc  = (t * w * l) / 12
            tot_bf = bf_pc * q
            wst_bf = tot_bf * (1 + wst)
            cost   = wst_bf * prc
            lin_ft = l * q
            self._lm_bfpc.set(f"{bf_pc:,.3f} BF");    self._lm_totbf.set(f"{tot_bf:,.3f} BF")
            self._lm_wastbf.set(f"{wst_bf:,.3f} BF"); self._lm_cost.set(f"${cost:,.2f}" if prc else "—")
            self._lm_linft.set(f"{lin_ft:,.1f} ft")
            self._lb_diag = dict(t=t, w=w, l=l)
            self._draw_lb_diagram()
        except Exception as e: self._lm_bfpc.set(f"Error: {e}")

    # ── BATTEN SPACING ────────────────────────────────────
    def _build_batten(self):
        inner, res = self._two_col(self._all_frames["Batten"])
        self._bt_span  = self._le(inner, "Total Span (ft)",                  "12")
        self._bt_width = self._le(inner, "Batten Width (in)",                "2")
        self._bt_gap   = self._le(inner, "Desired Gap Between Battens (in)", "6")
        self._bt_rows  = self._le(inner, "Number of Rows / Runs",            "1")
        calc_button(inner, "Calculate →", self._calc_batten, clear_cmd=self._clear_batten, sample_cmd=self._sample_batten)

        self._ba_n    = tk.StringVar(value="—"); self._ba_gap  = tk.StringVar(value="—")
        self._ba_ctc  = tk.StringVar(value="—"); self._ba_tot  = tk.StringVar(value="—")
        self._ba_first= tk.StringVar(value="—"); self._ba_chk  = tk.StringVar(value="—")
        self._rr(res, "Battens per Row",               self._ba_n,    ACCENT)
        self._rr(res, "Actual Gap (in)",               self._ba_gap)
        self._rr(res, "Center-to-Center Spacing (in)", self._ba_ctc)
        self._rr(res, "First Batten from Edge",        self._ba_first)
        self._rr(res, "Total Battens (all rows)",      self._ba_tot)
        self._rr(res, "Span Check",                    self._ba_chk)

    def _calc_batten(self):
        try:
            span_ft = float(self._bt_span.get())
            bw      = float(self._bt_width.get())
            des_gap = float(self._bt_gap.get())
            rows    = int(float(self._bt_rows.get()))
            span_in = span_ft * 12
            n       = round((span_in + des_gap) / (bw + des_gap))
            n       = max(2, n)
            act_gap = (span_in - n * bw) / (n - 1)
            ctc     = bw + act_gap
            check   = n * bw + (n - 1) * act_gap
            self._ba_n.set(str(n))
            self._ba_gap.set(f'{act_gap:.4f}"  ({inches_to_ruler(act_gap)})')
            self._ba_ctc.set(f'{ctc:.4f}"  ({inches_to_ruler(ctc)})')
            self._ba_first.set('0"  (flush with edge)')
            self._ba_tot.set(str(n * rows))
            ok = "✓" if abs(check - span_in) < 0.001 else "⚠"
            self._ba_chk.set(f'Total: {check:.3f}"  {ok}')
            self._bt_diag = dict(n=n, span=span_in, bw=bw, gap=act_gap)
            self._draw_bt_diagram()
        except Exception as e: self._ba_n.set(f"Error: {e}")

    # ── COVER BOARDING ────────────────────────────────────
    def _build_coverboard(self):
        inner, res = self._two_col(self._all_frames["Overlapping Boards"])
        self._cb_sw    = self._le_ft(inner, "Surface Width (ft)",          "10")
        self._cb_blen  = self._le(inner,    "Board Length (ft)",           "8")
        self._cb_bbw   = self._le(inner,    "Bottom Board Width (in)",     "5.5")
        self._cb_cbw   = self._le(inner,    "Cover Board Width (in)",      "3.5")
        self._cb_olap  = self._le(inner,    "Overlap per Side (in)",       "0.75")
        self._cb_waste = self._le(inner,    "Waste Factor (%)",            "10")
        calc_button(inner, "Calculate →", self._calc_coverboard, clear_cmd=self._clear_coverboard, sample_cmd=self._sample_coverboard)

        self._cv_nb   = tk.StringVar(value="—"); self._cv_nc  = tk.StringVar(value="—")
        self._cv_tot  = tk.StringVar(value="—"); self._cv_vis = tk.StringVar(value="—")
        self._cv_lin  = tk.StringVar(value="—"); self._cv_pat = tk.StringVar(value="—")
        self._cv_chk  = tk.StringVar(value="—")
        self._rr(res, "Bottom Boards needed",          self._cv_nb,  ACCENT)
        self._rr(res, "Cover Boards needed",           self._cv_nc,  ACCENT)
        self._rr(res, "Total Boards (with waste)",     self._cv_tot)
        self._rr(res, "Visible Bottom Board (in)",     self._cv_vis)
        self._rr(res, "Total Linear Feet (with waste)",self._cv_lin)
        self._rr(res, "Pattern Repeat Width (in)",     self._cv_pat)
        self._rr(res, "Coverage Check",                self._cv_chk)

    def _calc_coverboard(self):
        try:
            sw    = float(self._cb_sw.get())
            blen  = float(self._cb_blen.get())
            bbw   = float(self._cb_bbw.get())   # bottom board width (in)
            cbw   = float(self._cb_cbw.get())   # cover board width (in)
            olap  = float(self._cb_olap.get())  # overlap per side (in)
            waste = float(self._cb_waste.get()) / 100
            sw_in = sw * 12
            n_bot = math.ceil(sw_in / bbw)
            n_cov = n_bot - 1                   # one cover per joint
            visible = bbw - 2 * olap            # visible bottom board between covers
            pattern = bbw                       # each bottom board = one pattern repeat
            total_base = n_bot + n_cov
            total_w    = math.ceil(total_base * (1 + waste))
            lin_ft     = total_w * blen
            actual_cov = n_bot * bbw
            ok = "✓" if abs(actual_cov - sw_in) <= bbw else f"⚠  {actual_cov/12:.2f} ft covered"
            self._cv_nb.set(str(n_bot))
            self._cv_nc.set(str(n_cov))
            self._cv_tot.set(str(total_w))
            self._cv_vis.set(f'{visible:.3f}"' if visible > 0 else "⚠  Overlap too large")
            self._cv_lin.set(f"{lin_ft:,.1f} ft")
            self._cv_pat.set(f'{pattern:.3f}"')
            self._cv_chk.set(ok)
            self._cb_diag = dict(bbw=bbw, cbw=cbw, olap=olap, visible=visible)
            self._draw_cb_diagram()
        except Exception as e: self._cv_nb.set(f"Error: {e}")

    # ── DECKING ───────────────────────────────────────────
    def _build_decking(self):
        inner, res = self._two_col(self._all_frames["Decking"])
        self._dk_len   = self._le(inner, "Deck Length (ft)",           "16")
        self._dk_wid   = self._le(inner, "Deck Width (ft)",            "12")
        self._dk_dir   = self._lo(inner, "Board Direction",
                                  ["Boards run across width",
                                   "Boards run along length",
                                   "45° diagonal — Left (\\)",
                                   "45° diagonal — Right (/)"],
                                  default="Boards run across width")
        self._dk_blen  = self._le(inner, "Board Length (ft)",          "16")
        self._dk_bwid  = self._le(inner, "Board Width — actual (in)",  "5.5")
        self._dk_bthk  = self._le(inner, "Board Thickness (in)",       "1.5")
        self._dk_gap   = self._le(inner, "Gap Between Boards (in)",    "0.25")
        self._dk_joist = self._le(inner, "Joist Spacing (in)",         "16")
        self._dk_waste = self._le(inner, "Waste Factor (%)",           "10")
        calc_button(inner, "Calculate →", self._calc_decking, clear_cmd=self._clear_decking, sample_cmd=self._sample_decking)

        self._dc_rows = tk.StringVar(value="—"); self._dc_bpr  = tk.StringVar(value="—")
        self._dc_tot  = tk.StringVar(value="—"); self._dc_lin  = tk.StringVar(value="—")
        self._dc_bf   = tk.StringVar(value="—"); self._dc_jst  = tk.StringVar(value="—")
        self._dc_area = tk.StringVar(value="—"); self._dc_cvg  = tk.StringVar(value="—")
        self._rr(res, "Board Rows Across Width",      self._dc_rows, ACCENT)
        self._rr(res, "Boards per Row (lengthwise)",  self._dc_bpr)
        self._rr(res, "Total Boards (with waste)",    self._dc_tot)
        self._rr(res, "Total Linear Feet",            self._dc_lin)
        self._rr(res, "Total Board Feet",             self._dc_bf)
        self._rr(res, "Joists Needed",                self._dc_jst)
        self._rr(res, "Deck Area (sq ft)",            self._dc_area)
        self._rr(res, "Coverage per Row (in)",        self._dc_cvg)

    def _calc_decking(self):
        try:
            dl    = float(self._dk_len.get());   dw    = float(self._dk_wid.get())
            blen  = float(self._dk_blen.get());  bwid  = float(self._dk_bwid.get())
            bthk  = float(self._dk_bthk.get());  gap   = float(self._dk_gap.get())
            joist = float(self._dk_joist.get()); waste = float(self._dk_waste.get()) / 100
            cov_in = bwid + gap
            dk_dir = self._dk_dir.get()
            if "45" in dk_dir:
                direction = "45r" if "Right" in dk_dir else "45l"
                diag_ft   = math.sqrt(dl**2 + dw**2)
                n_rows    = math.ceil((dl + dw) * 12 / math.sqrt(2) / cov_in)
                boards_pr = math.ceil(diag_ft / blen)
                total     = math.ceil(n_rows * boards_pr * (1 + waste))
                lin_ft    = n_rows * diag_ft * (1 + waste)
                total_bf  = total * (bthk * bwid * blen) / 12
                n_joists  = math.floor(max(dl, dw) / (joist / 12)) + 1
            elif "along" in dk_dir:
                direction = "along"
                n_rows    = math.ceil(dl / (cov_in / 12))
                boards_pr = math.ceil(dw / blen)
                total     = math.ceil(n_rows * boards_pr * (1 + waste))
                lin_ft    = n_rows * dw * (1 + waste)
                total_bf  = total * (bthk * bwid * blen) / 12
                n_joists  = math.floor(dw / (joist / 12)) + 1
            else:
                direction = "across"
                n_rows    = math.ceil(dw / (cov_in / 12))
                boards_pr = math.ceil(dl / blen)
                total     = math.ceil(n_rows * boards_pr * (1 + waste))
                lin_ft    = n_rows * dl * (1 + waste)
                total_bf  = total * (bthk * bwid * blen) / 12
                n_joists  = math.floor(dl / (joist / 12)) + 1
            self._dc_rows.set(str(n_rows))
            self._dc_bpr.set(str(boards_pr))
            self._dc_tot.set(str(total))
            self._dc_lin.set(f"{lin_ft:,.2f} ft")
            self._dc_bf.set(f"{total_bf:,.2f} BF")
            self._dc_jst.set(str(n_joists))
            self._dc_area.set(f"{dl * dw:,.2f} sq ft")
            self._dc_cvg.set(f'{cov_in:.3f}"  ({inches_to_ruler(cov_in)})')
            self._dk_diag = dict(dl=dl, dw=dw, bwid=bwid, gap=gap,
                                 joist=joist, blen=blen, direction=direction)
            self._draw_dk_diagram()
        except Exception as e: self._dc_rows.set(f"Error: {e}")


    # ── CLEAR HELPERS ─────────────────────────────────────────────
    def _clr(self, inv, outv, canvas_attr=None, diag_attr=None):
        """Clear input vars to '' and result vars to '—'."""
        for v in inv:  v.set("")
        for v in outv: v.set("—")
        if diag_attr: setattr(self, diag_attr, None)
        if canvas_attr:
            cv = getattr(self, canvas_attr, None)
            if cv:
                cv.delete("all")
                W = getattr(self, canvas_attr+"_w", 0) or cv.winfo_width() or 500
                H = int(cv.cget("height"))
                self._dph(cv, W, H)

    def _clear_area(self):
        for lbl,var in self._area_ivars.items(): var.set("")
        for v in [self._a_sqft,self._a_sqin,self._a_sqyd,self._a_sqm,self._a_perim]: v.set("—")
        self._area_diag=None
        if hasattr(self,"_area_cv"): self._area_cv.delete("all"); self._dph(self._area_cv, getattr(self,"_area_cv_w",500) or 500, int(self._area_cv.cget("height")))

    def _clear_volume(self):
        for lbl,var in self._vol_ivars.items(): var.set("")
        for v in [self._v_cuft,self._v_cuin,self._v_cuyd,self._v_cum,self._v_gal,self._v_sa]: v.set("—")
        self._vol_diag=None
        if hasattr(self,"_vol_cv"): self._vol_cv.delete("all"); self._dph(self._vol_cv, getattr(self,"_vol_cv_w",500) or 500, int(self._vol_cv.cget("height")))

    def _clear_stairs(self):
        for v in [self._st_rise,self._st_des_r,self._st_tread,self._st_nose]: v.set("")
        for v in [self._st_nris,self._st_arise,self._st_ntrd,self._st_trun,
                  self._st_trun_ft,self._st_slen,self._st_nose_v,self._st_ang,self._st_ang2,self._st_code]: v.set("—")
        self._st_diag=None
        if hasattr(self,"_st_cv"): self._st_cv.delete("all"); self._dph(self._st_cv, getattr(self,"_st_cv_w",500) or 500, int(self._st_cv.cget("height")))

    def _clear_concrete(self):
        for lbl,var in self._conc_ivars.items(): var.set("")
        self._cn_waste.set("")
        for v in [self._cn_cuft,self._cn_cuyd,self._cn_cuftw,self._cn_cuydw,self._cn_b60,self._cn_b80]: v.set("—")
        self._cn_diag=None
        if hasattr(self,"_cn_cv"): self._cn_cv.delete("all"); self._dph(self._cn_cv, getattr(self,"_cn_cv_w",500) or 500, int(self._cn_cv.cget("height")))

    def _clear_roofing(self):
        for v in [self._rf_len,self._rf_wid,self._rf_pitch,self._rf_waste]: v.set("")
        for v in [self._rf_flat,self._rf_act,self._rf_sq,self._rf_sqw,self._rf_raft,self._rf_ridge,self._rf_ang]: v.set("—")
        self._rf_diag=None
        if hasattr(self,"_rf_cv"): self._rf_cv.delete("all"); self._dph(self._rf_cv, getattr(self,"_rf_cv_w",500) or 500, int(self._rf_cv.cget("height")))

    def _clear_lumber(self):
        for v in [self._lb_thick,self._lb_width,self._lb_len,self._lb_qty,self._lb_waste,self._lb_price]: v.set("")
        for v in [self._lm_bfpc,self._lm_totbf,self._lm_wastbf,self._lm_cost,self._lm_linft]: v.set("—")
        self._lb_diag=None
        if hasattr(self,"_lb_cv"): self._lb_cv.delete("all"); self._dph(self._lb_cv, getattr(self,"_lb_cv_w",500) or 500, int(self._lb_cv.cget("height")))

    def _clear_batten(self):
        for v in [self._bt_span,self._bt_width,self._bt_gap,self._bt_rows]: v.set("")
        for v in [self._ba_n,self._ba_gap,self._ba_ctc,self._ba_first,self._ba_tot,self._ba_chk]: v.set("—")
        self._bt_diag=None
        if hasattr(self,"_bt_cv"): self._bt_cv.delete("all"); self._dph(self._bt_cv, getattr(self,"_bt_cv_w",500) or 500, int(self._bt_cv.cget("height")))

    def _clear_coverboard(self):
        for v in [self._cb_sw,self._cb_blen,self._cb_bbw,self._cb_cbw,self._cb_olap,self._cb_waste]: v.set("")
        for v in [self._cv_nb,self._cv_nc,self._cv_tot,self._cv_vis,self._cv_lin,self._cv_pat,self._cv_chk]: v.set("—")
        self._cb_diag=None
        if hasattr(self,"_cb_cv"): self._cb_cv.delete("all"); self._dph(self._cb_cv, getattr(self,"_cb_cv_w",500) or 500, int(self._cb_cv.cget("height")))

    def _clear_decking(self):
        self._dk_dir.set("Boards run across width")
        for v in [self._dk_len,self._dk_wid,self._dk_blen,self._dk_bwid,self._dk_bthk,
                  self._dk_gap,self._dk_joist,self._dk_waste]: v.set("")
        for v in [self._dc_rows,self._dc_bpr,self._dc_tot,self._dc_lin,self._dc_bf,
                  self._dc_jst,self._dc_area,self._dc_cvg]: v.set("—")
        self._dk_diag=None
        if hasattr(self,"_dk_cv"): self._dk_cv.delete("all"); self._dph(self._dk_cv, getattr(self,"_dk_cv_w",500) or 500, int(self._dk_cv.cget("height")))


    # ── SAMPLE DATA RESTORERS ─────────────────────────────────────
    def _sample_area(self):
        for lbl,dflt in self.AREA_SHAPES.get(self._area_shape.get(),[]):
            if lbl in self._area_ivars: self._area_ivars[lbl].set(dflt)
    def _sample_volume(self):
        for lbl,dflt in self.VOL_SHAPES.get(self._vol_shape.get(),[]):
            if lbl in self._vol_ivars: self._vol_ivars[lbl].set(dflt)
    def _sample_concrete(self):
        for lbl,dflt in self.CONC_SHAPES.get(self._conc_shape.get(),[]):
            if lbl in self._conc_ivars: self._conc_ivars[lbl].set(dflt)
        self._cn_waste.set("10")
    def _sample_stairs(self):
        self._st_rise.set("108"); self._st_des_r.set("7.0")
        self._st_tread.set("11.25"); self._st_nose.set("0.75")
    def _sample_roofing(self):
        self._rf_len.set("40"); self._rf_wid.set("30")
        self._rf_pitch.set("6"); self._rf_waste.set("10")
    def _sample_lumber(self):
        self._lb_thick.set("1.5"); self._lb_width.set("3.5")
        self._lb_len.set("8"); self._lb_qty.set("10")
        self._lb_waste.set("10"); self._lb_price.set("0")
    def _sample_batten(self):
        self._bt_span.set("12"); self._bt_width.set("2")
        self._bt_gap.set("6"); self._bt_rows.set("1")
    def _sample_coverboard(self):
        self._cb_sw.set("10"); self._cb_blen.set("8")
        self._cb_bbw.set("5.5"); self._cb_cbw.set("3.5")
        self._cb_olap.set("0.75"); self._cb_waste.set("10")
    def _sample_decking(self):
        self._dk_len.set("16"); self._dk_wid.set("12")
        self._dk_blen.set("16"); self._dk_bwid.set("5.5")
        self._dk_bthk.set("1.5"); self._dk_gap.set("0.25")
        self._dk_joist.set("16"); self._dk_waste.set("10")


    # ════════════════════════════════════════════════════════
    # LIVE DIAGRAMS
    # ════════════════════════════════════════════════════════

    def _make_diagram_canvas(self, parent, height=180):
        card = make_card(parent)
        card.pack(fill="x", padx=10, pady=(0, 10))
        section_header(card, "  LIVE DIAGRAM")
        cv = tk.Canvas(card, height=height, bg="#FAFBFD",
                       highlightthickness=1, highlightbackground=BORDER)
        cv.pack(fill="x", padx=10, pady=(0, 10))
        return cv

    def _add_all_diagrams(self):
        specs = [
            ("Area",              "_area_cv", 190, self._on_area_cfg),
            ("Batten",            "_bt_cv",   160, self._on_bt_cfg),
            ("Concrete",          "_cn_cv",   190, self._on_cn_cfg),
            ("Overlapping Boards","_cb_cv",   200, self._on_cb_cfg),
            ("Decking",           "_dk_cv",   360, self._on_dk_cfg),
            ("Lumber",            "_lb_cv",   160, self._on_lb_cfg),
            ("Roofing",           "_rf_cv",   210, self._on_rf_cfg),
            ("Stairs",            "_st_cv",   380, self._on_st_cfg),
            ("Volume",            "_vol_cv",  190, self._on_vol_cfg),
            ("Corner Angle",      "_ca_cv",   200, self._on_ca_cfg),
            ("Crown Molding",     "_cm_cv",   260, self._on_cm_cfg),
            ("Diagonal",          "_dg_cv",   200, self._on_dg_cfg),
            ("Miter Joint",       "_mj_cv",   240, self._on_mj_cfg),
            ("Parquet Floor",     "_pq_cv",   300, self._on_pq_cfg),
            ("Ramp",              "_rp_cv",   190, self._on_rp_cfg),
            ("Slope",             "_sl_cv",   180, self._on_sl_cfg),
        ]
        for tn, attr, h, handler in specs:
            cv = self._make_diagram_canvas(self._all_frames[tn], h)
            setattr(self, attr, cv); setattr(self, attr+"_w", 0)
            cv.bind("<Configure>", handler)

    @staticmethod
    def _dph(c, W, H):
        c.create_text(W//2, H//2, text="Calculate to see diagram",
                      fill=MUTED, font=("Segoe UI", 10))

    @staticmethod
    def _ha(c, x1, y, x2, clr="#1F3864", lbl="", above=True):
        if abs(x2-x1) < 6: return
        c.create_line(x1+2, y, x2-2, y, fill=clr, width=1, arrow="both")
        if lbl:
            c.create_text((x1+x2)/2, y-9 if above else y+9,
                          text=lbl, fill=clr, font=("Segoe UI", 8))

    @staticmethod
    def _va(c, x, y1, y2, clr="#1F3864", lbl="", right=True):
        if abs(y2-y1) < 6: return
        c.create_line(x, y1+2, x, y2-2, fill=clr, width=1, arrow="both")
        if lbl:
            c.create_text(x+9 if right else x-9, (y1+y2)/2,
                          text=lbl, fill=clr, font=("Segoe UI", 8),
                          anchor="w" if right else "e")

    # ── AREA ──────────────────────────────────────────────
    def _on_area_cfg(self, event):
        self._area_cv_w = event.width; self._draw_area_diagram()

    def _draw_area_diagram(self):
        c = self._area_cv; c.delete("all")
        W = getattr(self,"_area_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self, "_area_diag", None)
        if not d: self._dph(c,W,H); return
        shape=d["shape"]; MX=W//2; MY=H//2
        F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; PAD=50

        if shape == "Rectangle":
            rw=d["w"]; rh=d["h"]; sc=min((W-2*PAD)/(rw or 1),(H-60)/(rh or 1))
            pw=rw*sc; ph=rh*sc; x0=MX-pw/2; y0=MY-ph/2
            c.create_rectangle(x0,y0,x0+pw,y0+ph,fill=F,outline=O,width=2)
            self._ha(c,x0,y0-12,x0+pw,DIM,f"{rw} ft")
            self._va(c,x0+pw+12,y0,y0+ph,DIM,f"{rh} ft")
        elif shape == "Square":
            s=d["s"]; sc=min((W-2*PAD)/(s or 1),(H-60)/(s or 1))
            ps=s*sc; c.create_rectangle(MX-ps/2,MY-ps/2,MX+ps/2,MY+ps/2,fill=F,outline=O,width=2)
            self._ha(c,MX-ps/2,MY-ps/2-12,MX+ps/2,DIM,f"{s} ft")
        elif shape == "Triangle":
            b=d["b"]; h=d["ht"]; sc=min((W-2*PAD)/(b or 1),(H-60)/(h or 1))
            pb=b*sc; ph=h*sc; bx=MX; by=MY+ph/2
            c.create_polygon([bx-pb/2,by,bx+pb/2,by,bx,by-ph],fill=F,outline=O,width=2)
            self._ha(c,bx-pb/2,by+12,bx+pb/2,DIM,f"b={b} ft",above=False)
            c.create_line(bx,by,bx,by-ph,fill=DIM,width=1,dash=(4,3))
            self._va(c,bx+pb/4+10,by-ph,by,DIM,f"h={h} ft")
        elif shape == "Right Triangle":
            la=d["la"]; lb=d["lb"]; hyp=d["hyp"]
            sc=min((W-2*PAD)/(la or 1),(H-60)/(lb or 1))
            pla=la*sc; plb=lb*sc; x0=MX-pla/2; y0=MY+plb/2
            c.create_polygon([x0,y0,x0+pla,y0,x0,y0-plb],fill=F,outline=O,width=2)
            sq=10; c.create_rectangle(x0,y0-sq,x0+sq,y0,outline=O,fill="")
            self._ha(c,x0,y0+12,x0+pla,DIM,f"A={la} ft",above=False)
            self._va(c,x0-12,y0-plb,y0,DIM,f"B={lb} ft",right=False)
            c.create_text((x0+x0+pla)/2+12,(y0+y0-plb)/2-6,
                          text=f"C={hyp:.2f} ft",fill=DIM,font=("Segoe UI",8))
        elif shape == "Circle":
            r=d["r"]; pr=min((W-2*PAD)/2,(H-40)/2)*0.85
            c.create_oval(MX-pr,MY-pr,MX+pr,MY+pr,fill=F,outline=O,width=2)
            c.create_line(MX,MY,MX+pr,MY,fill=DIM,width=1)
            c.create_oval(MX-3,MY-3,MX+3,MY+3,fill=DIM,outline=DIM)
            c.create_text(MX+pr/2,MY-12,text=f"r={r} ft",fill=DIM,font=("Segoe UI",9))
        elif shape == "Trapezoid":
            sa=d["sa"]; sb=d["sb"]; h=d["ht"]
            sc=min((W-2*PAD)/(max(sa,sb) or 1),(H-60)/(h or 1))
            pa=sa*sc; pb=sb*sc; ph=h*sc
            c.create_polygon([MX-pb/2,MY+ph/2,MX+pb/2,MY+ph/2,
                               MX+pa/2,MY-ph/2,MX-pa/2,MY-ph/2],fill=F,outline=O,width=2)
            self._ha(c,MX-pa/2,MY-ph/2-12,MX+pa/2,DIM,f"A={sa} ft")
            self._ha(c,MX-pb/2,MY+ph/2+12,MX+pb/2,DIM,f"B={sb} ft",above=False)
            self._va(c,MX+pb/2+12,MY-ph/2,MY+ph/2,DIM,f"h={h} ft")
        elif shape == "Ellipse":
            ea=d["ea"]; eb=d["eb"]
            sc=min((W-2*PAD)/(2*ea or 1),(H-40)/(2*eb or 1))
            pea=ea*sc; peb=eb*sc
            c.create_oval(MX-pea,MY-peb,MX+pea,MY+peb,fill=F,outline=O,width=2)
            c.create_line(MX,MY,MX+pea,MY,fill=DIM,width=1)
            c.create_line(MX,MY,MX,MY-peb,fill=DIM,width=1)
            c.create_text(MX+pea/2,MY+8,text=f"a={ea} ft",fill=DIM,font=("Segoe UI",8))
            c.create_text(MX-28,MY-peb/2,text=f"b={eb} ft",fill=DIM,font=("Segoe UI",8))

    # ── BATTEN ────────────────────────────────────────────
    def _on_bt_cfg(self, event):
        self._bt_cv_w = event.width; self._draw_bt_diagram()

    def _draw_bt_diagram(self):
        c = self._bt_cv; c.delete("all")
        W = getattr(self,"_bt_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_bt_diag",None)
        if not d: self._dph(c,W,H); return
        n=d["n"]; span=d["span"]; bw=d["bw"]; gap=d["gap"]
        PAD=40; WALL_Y=H-20; BOT=WALL_Y-8; TOP=BOT-45; MID=(TOP+BOT)//2; ARW_Y=BOT+14
        scale=(W-2*PAD)/(span or 1); bwpx=bw*scale; gapx=gap*scale
        c.create_line(PAD,WALL_Y,W-PAD,WALL_Y,fill="#555",width=2)
        c.create_line(PAD,WALL_Y-5,PAD,WALL_Y+5,fill="#555",width=2)
        c.create_line(W-PAD,WALL_Y-5,W-PAD,WALL_Y+5,fill="#555",width=2)
        c.create_text(W//2,WALL_Y+12,
                      text=f'Span: {inches_to_ruler(span)} ({inches_to_feet(span)})',
                      fill=MUTED,font=("Segoe UI",8))
        x=PAD
        for i in range(n):
            x0,x1=x,x+bwpx; cx=(x0+x1)/2
            c.create_rectangle(x0,TOP,x1,BOT,fill=RES_BG,outline="#1565C0",width=2)
            if bwpx>14: c.create_text(cx,MID,text=str(i+1),fill="#1565C0",font=("Segoe UI",9,"bold"))
            if i==0 and bwpx>20:
                c.create_text(cx,TOP-10,text=inches_to_ruler(bw),fill="#333",font=("Segoe UI",8))
            if i>0 and gapx>8:
                self._ha(c,x0-gapx,ARW_Y,x0,"#1F3864",inches_to_ruler(gap) if gapx>26 else "",above=False)
            x+=bwpx+gapx
        if gapx>8:
            self._ha(c,x-gapx,ARW_Y,W-PAD,"#1F3864",inches_to_ruler(gap) if gapx>26 else "",above=False)

    # ── CONCRETE ──────────────────────────────────────────
    def _on_cn_cfg(self, event):
        self._cn_cv_w = event.width; self._draw_cn_diagram()

    def _draw_cn_diagram(self):
        c = self._cn_cv; c.delete("all")
        W = getattr(self,"_cn_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_cn_diag",None)
        if not d: self._dph(c,W,H); return
        shape=d["shape"]; MX=W//2; MY=H//2; F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; OFF=14

        if shape == "Slab":
            L=d["L"]; Wd=d["W"]; T=d["T"]
            sc=min((W-100)/(L or 1),(H-80)/(Wd or 1))*0.7
            pw=L*sc; ph=Wd*sc; x0=MX-pw/2-OFF//2; y0=MY-ph/2
            c.create_rectangle(x0,y0+OFF,x0+pw,y0+ph+OFF,fill=F,outline=O,width=2)
            c.create_polygon([x0,y0+OFF,x0+OFF,y0,x0+pw+OFF,y0,x0+pw,y0+OFF],fill=INPUT_BG,outline=O,width=2)
            c.create_polygon([x0+pw,y0+OFF,x0+pw+OFF,y0,x0+pw+OFF,y0+ph,x0+pw,y0+ph+OFF],fill="#C8DCF0",outline=O,width=2)
            self._ha(c,x0,y0+ph+OFF+12,x0+pw,DIM,f"L={L} ft",above=False)
            self._va(c,x0-12,y0+OFF,y0+ph+OFF,DIM,f"W={Wd} ft",right=False)
            c.create_text(x0+pw+OFF+4,y0+ph//2,text=f'T={T}"',fill=DIM,font=("Segoe UI",8),anchor="w")
        elif shape == "Circular Slab":
            dia=d["D"]; T=d["T"]
            pr=min((W-2*50)/2,(H-60)/2)*0.7
            c.create_oval(MX-pr,MY-pr*0.4,MX+pr,MY+pr*0.4,fill=F,outline=O,width=2)
            c.create_oval(MX-pr,MY-pr*0.4+OFF,MX+pr,MY+pr*0.4+OFF,outline=O,width=1)
            c.create_line(MX-pr,MY-pr*0.4,MX-pr,MY-pr*0.4+OFF,fill=O,width=1)
            c.create_line(MX+pr,MY-pr*0.4,MX+pr,MY-pr*0.4+OFF,fill=O,width=1)
            self._ha(c,MX,MY-pr*0.4-14,MX+pr,DIM,f"D={dia} ft")
            c.create_text(MX+pr+6,MY,text=f'T={T}"',fill=DIM,font=("Segoe UI",8),anchor="w")
        elif shape == "Column":
            dia=d["D"]; ht=d["H"]
            rx=min((W-100)/4,45)
            sc=min((H-80)/(ht or 1),1); ph=min(ht*sc*8,H-60); ry=rx*0.35
            c.create_rectangle(MX-rx,MY-ph/2,MX+rx,MY+ph/2,fill=F,outline=O,width=2)
            c.create_oval(MX-rx,MY-ph/2-ry,MX+rx,MY-ph/2+ry,fill=F,outline=O,width=2)
            c.create_arc(MX-rx,MY+ph/2-ry,MX+rx,MY+ph/2+ry,start=0,extent=-180,outline=O,style="arc",width=1)
            self._ha(c,MX,MY-ph/2-ry-14,MX+rx,DIM,f'D={dia}"')
            self._va(c,MX+rx+12,MY-ph/2,MY+ph/2,DIM,f"H={ht} ft")
        elif shape == "Footing":
            Wd=d["Wi"]; Dp=d["Dp"]
            sc=0.55; pw=Wd*sc; ph=Dp*sc
            c.create_rectangle(MX-pw/2,MY-ph/2,MX+pw/2,MY+ph/2,fill=F,outline=O,width=2)
            self._ha(c,MX-pw/2,MY-ph/2-14,MX+pw/2,DIM,f'W={Wd}"')
            self._va(c,MX+pw/2+12,MY-ph/2,MY+ph/2,DIM,f'D={Dp}"')

    # ── COVER BOARD ───────────────────────────────────────
    def _on_cb_cfg(self, event):
        self._cb_cv_w = event.width; self._draw_cb_diagram()

    def _draw_cb_diagram(self):
        """Side elevation: BB on surface, CB spanning joints with overlap."""
        c = self._cb_cv; c.delete("all")
        W = getattr(self,"_cb_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_cb_diag",None)
        if not d: self._dph(c,W,H); return
        bbw=d["bbw"]; cbw=d["cbw"]; olap=d["olap"]; visible=d["visible"]
        n_bb=3; n_cb=2
        PAD=50; PAD_R=95; DW=W-PAD-PAD_R
        scale=(DW/(n_bb*bbw)) if bbw else 1
        bbw_px=bbw*scale; cbw_px=cbw*scale; olap_px=olap*scale
        SURF_Y=H-45; BB_H=22; CB_H=16
        BB_Y=SURF_Y-BB_H; CB_Y=BB_Y-CB_H-3
        F_BB="#D6E4F0"; F_BB2="#C0D8EC"; F_CB="#2F5496"; F_OV="#9BC0DC"
        OL="#1565C0"; DIM=DIAGRAM_DIM; OL_CB="#1F3864"

        # Ground line
        c.create_line(PAD-4,SURF_Y,W-PAD_R+4,SURF_Y,fill="#888",width=3)

        # Draw bottom boards
        for i in range(n_bb):
            x0=PAD+i*bbw_px; x1=x0+bbw_px
            c.create_rectangle(x0,BB_Y,x1,SURF_Y,
                               fill=F_BB if i%2==0 else F_BB2,outline=OL,width=2)
            if bbw_px>22:
                c.create_text((x0+x1)/2,(BB_Y+SURF_Y)/2,text=f"BB {i+1}",
                              fill=DIM,font=("Segoe UI",9,"bold"))

        # Draw overlap zones then cover boards
        for j in range(n_cb):
            jx=PAD+(j+1)*bbw_px
            x0=jx-cbw_px/2; x1=jx+cbw_px/2
            # Shade overlap on BB
            c.create_rectangle(x0,BB_Y,x0+olap_px,SURF_Y,fill=F_OV,outline="")
            c.create_rectangle(x1-olap_px,BB_Y,x1,SURF_Y,fill=F_OV,outline="")
        # Redraw BB outlines over shading
        for i in range(n_bb):
            x0=PAD+i*bbw_px; x1=x0+bbw_px
            c.create_rectangle(x0,BB_Y,x1,SURF_Y,fill="",outline=OL,width=2)
        # Draw cover boards on top
        for j in range(n_cb):
            jx=PAD+(j+1)*bbw_px
            x0=jx-cbw_px/2; x1=jx+cbw_px/2
            c.create_rectangle(x0,CB_Y,x1,BB_Y,fill=F_CB,outline=OL_CB,width=2)
            if cbw_px>22:
                c.create_text((x0+x1)/2,(CB_Y+BB_Y)/2,text=f"CB {j+1}",
                              fill="white",font=("Segoe UI",9,"bold"))

        # Dim arrows — BB width below surface
        self._ha(c,PAD,SURF_Y+14,PAD+bbw_px,DIM,f'BB {bbw:.2f}"',above=False)
        # CB width above cover board
        jx=PAD+bbw_px
        x0=jx-cbw_px/2; x1=jx+cbw_px/2
        self._ha(c,x0,CB_Y-14,x1,"#2F5496",f'CB {cbw:.2f}"')
        # Overlap on right side
        x_arr=W-PAD_R+12
        self._va(c,x_arr,CB_Y,BB_Y,DIM,f'CB {CB_H}px')
        # Overlap arrows under CB
        if olap_px>8:
            self._ha(c,x0,CB_Y-28,x0+olap_px,"#666",f'lap {olap:.2f}"')
        # Visible BB label
        if visible>0 and bbw_px-2*olap_px>14:
            vx0=PAD+olap_px+1; vx1=PAD+bbw_px-olap_px-1
            c.create_line(vx0,BB_Y-6,vx1,BB_Y-6,fill=ACCENT,width=1,arrow="both")
            c.create_text((vx0+vx1)/2,BB_Y-14,text=f'vis {visible:.2f}"',
                          fill=ACCENT,font=("Segoe UI",8))
        c.create_text(W//2,H-8,
                      text="Side elevation — cover boards span joints, overlap both bottom boards",
                      fill=MUTED,font=("Segoe UI",8))


    # ── DECKING ───────────────────────────────────────────
    def _on_dk_cfg(self, event):
        self._dk_cv_w = event.width; self._draw_dk_diagram()

    def _draw_dk_diagram(self):
        """Top-down decking: staggered rows, all green labels below deck."""
        c = self._dk_cv; c.delete("all")
        W = getattr(self,"_dk_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_dk_diag",None)
        if not d: self._dph(c,W,H); return
        dl=d["dl"]; dw=d["dw"]; bwid=d["bwid"]; gap=d["gap"]
        joist=d["joist"]; blen=d.get("blen", dl)
        cov=bwid+gap

        # Layout: TOP=34 for two header lines above deck
        PAD_L=90; PAD_R=120; TOP=34; BOT=84
        DW=W-PAD_L-PAD_R; DH=H-TOP-BOT
        if DW<20 or DH<20: return
        sc_x=DW/(dl or 1); sc_y=DH/(dw or 1)
        joist_px=joist/12*sc_x; cov_px=cov/12*sc_y; blen_px=blen*sc_x
        F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; GRN="#276749"
        deck_x0=PAD_L; deck_y0=TOP; deck_x1=PAD_L+DW; deck_y1=TOP+DH

        # ── Suggested gap: gap that evenly fills deck with no partial row ──
        n_r = math.ceil(dw * 12 / (bwid + gap)) if (bwid + gap) > 0 else 1
        sugg = dw * 12 / n_r - bwid if n_r > 0 else gap
        if sugg < 0:
            n_r = max(1, n_r - 1)
            sugg = dw * 12 / n_r - bwid if n_r > 0 else gap

        direction = d.get("direction", "across")

        # ── Deck background ───────────────────────────────────────
        c.create_rectangle(deck_x0,deck_y0,deck_x1,deck_y1,
                           fill="#F0F4F8",outline="#888",width=1)

        # ── Headers: across direction only ────────────────────────
        if direction == "across":
            c.create_text(deck_x0, 10,
                          text=f'Boards {bwid}"  |  Gaps {gap}"  |  Joists {joist}" o.c.',
                          fill="#444", font=("Segoe UI",9,"bold"), anchor="w")
            c.create_text(deck_x1, 10,
                          text=f'Suggested Gap Between Boards:  {inches_to_ruler(sugg)}',
                          fill=GRN, font=("Segoe UI",9,"bold"), anchor="e")
            c.create_text(deck_x1, 24,
                          text="Prevents stripping of the last row.",
                          fill=GRN, font=("Segoe UI",8), anchor="e")

        # ── Along-length: rotate axes (boards run top-to-bottom) ──
        if direction == "along":
            sc_x2 = DW / (dw or 1); sc_y2 = DH / (dl or 1)
            blen_px2 = blen * sc_y2; cov_px2 = cov / 12 * sc_x2
            x = deck_x0; col = 0
            while x < deck_x1 and col < 80:
                bw2 = max(2, bwid / 12 * sc_x2); cx1 = min(x + bw2, deck_x1)
                offset_py = (blen_px2 / 2) if col % 2 == 1 else 0.0
                j = 0
                while True:
                    by0 = deck_y0 - offset_py + j * blen_px2
                    if by0 >= deck_y1: break
                    dy0 = max(deck_y0, by0); dy1 = min(deck_y1, by0 + blen_px2)
                    if dy0 < dy1:
                        c.create_rectangle(x, dy0, cx1, dy1, fill=F, outline=O, width=1)
                    if deck_y0 + 1 < by0 < deck_y1 - 1:
                        c.create_line(x, by0, cx1, by0, fill=GRN, width=2)
                    j += 1
                x += cov_px2; col += 1
            c.create_rectangle(deck_x0, deck_y0, deck_x1, deck_y1, fill="", outline=O, width=2)
            ax = deck_x0 - 22; mid_y = (deck_y0 + deck_y1) / 2
            c.create_line(ax, deck_y0+2, ax, deck_y1-2, fill=DIM, width=1, arrow="both")
            c.create_text(ax-6, mid_y-8, text="Length", fill=DIM, font=("Segoe UI",9,"bold"), anchor="e")
            c.create_text(ax-6, mid_y+8, text=f"{dl} ft", fill=DIM, font=("Segoe UI",9), anchor="e")
            c.create_text(deck_x0, 10, fill="#444", font=("Segoe UI",9,"bold"), anchor="w",
                          text=f'Boards {bwid}"  |  Gaps {gap}"  |  Direction: along length')
            ann_row = lambda yl,x0a,x1a,lbl,col,dsh=False: (
                c.create_line(x0a+2,yl,x1a-2,yl,fill=col,width=2 if not dsh else 1,arrow="both",dash=(4,3) if dsh else ()),
                c.create_text((x0a+x1a)/2,yl-10,text=lbl,fill=col,font=("Segoe UI",9,"bold" if not dsh else "normal")))
            r1=deck_y1+22; r2=deck_y1+46; r3=deck_y1+70
            ann_row(r1,deck_x0,deck_x0+min(blen_px2,DW),f"Board length: {blen} ft",GRN)
            ann_row(r2,deck_x0,deck_x0+min(blen_px2/2,DW),f"½ stagger: {blen/2:.2f} ft",GRN,dsh=True)
            ann_row(r3,deck_x0,deck_x1,f"Deck length: {dl} ft",DIM)
            return

        # ── 45° diagonal ──────────────────────────────────────────────────────
        if direction in ("45l","45r"):
            import math as _dm
            slash = (direction == "45r")
            sc_avg = (sc_x + sc_y) / 2
            step_c = (bwid + gap) / 12 * sc_avg * _dm.sqrt(2)
            bw_c   = bwid / 12 * sc_avg * _dm.sqrt(2)
            blen_c = blen * sc_avg  # blen in ft, sc_avg in px/ft
            def _ix(x0i,y0i,x1i,y1i,cv,sl):
                pts = []
                def chk(x,y):
                    if x0i<=x<=x1i and y0i<=y<=y1i: pts.append((x,y))
                if sl:
                    chk(cv-y0i,y0i); chk(cv-y1i,y1i); chk(x0i,cv-x0i); chk(x1i,cv-x1i)
                else:
                    chk(y0i-cv,y0i); chk(y1i-cv,y1i); chk(x0i,x0i+cv); chk(x1i,x1i+cv)
                seen=set(); u=[]
                for p in pts:
                    k=(round(p[0]),round(p[1]))
                    if k not in seen: seen.add(k); u.append(p)
                return u[:2]
            c_start = (deck_x0+deck_y0) if slash else (deck_y0-deck_x1)
            c_end   = (deck_x1+deck_y1) if slash else (deck_y1-deck_x0)
            n_s = int((c_end-c_start)/step_c)+3 if step_c>0 else 1
            # Draw filled strips using original theme colors (RES_BG + blue outline)
            for k in range(-1, n_s+1):
                c1=c_start+k*step_c; c2=c1+bw_c
                p1=_ix(deck_x0,deck_y0,deck_x1,deck_y1,c1,slash)
                p2=_ix(deck_x0,deck_y0,deck_x1,deck_y1,c2,slash)
                if len(p1)==2 and len(p2)==2:
                    flat=[v for pt in p1+list(reversed(p2)) for v in pt]
                    c.create_polygon(flat, fill=F, outline="")  # F=RES_BG blue
            # Stripe separators
            for k in range(-1, n_s+1):
                c1=c_start+k*step_c
                p1=_ix(deck_x0,deck_y0,deck_x1,deck_y1,c1,slash)
                if len(p1)==2:
                    c.create_line(p1[0][0],p1[0][1],p1[1][0],p1[1][1], fill=O, width=1)
            # Per-stripe staggered board-end cuts (Liang-Barsky clipped)
            def _lc(ax,ay,bx,by):
                """Liang-Barsky clip to deck bounds; returns (ax,ay,bx,by) or None."""
                dx=bx-ax; dy=by-ay; t0=0.0; t1=1.0
                for p,q in [(-dx,ax-deck_x0),(dx,deck_x1-ax),
                            (-dy,ay-deck_y0),(dy,deck_y1-ay)]:
                    if p==0:
                        if q<0: return None
                    elif p<0:
                        r=q/p
                        if r>t1: return None
                        if r>t0: t0=r
                    else:
                        r=q/p
                        if r<t0: return None
                        if r<t1: t1=r
                return ax+t0*dx,ay+t0*dy,ax+t1*dx,ay+t1*dy
            if blen_c > 4:
                if slash: cut_st2=deck_y0-deck_x1; cut_en2=deck_y1-deck_x0
                else:     cut_st2=deck_x0+deck_y0; cut_en2=deck_x1+deck_y1
                for k2 in range(-1,n_s+1):
                    c1k=c_start+k2*step_c; c2k=c1k+bw_c
                    n_c2=int((cut_en2-cut_st2)/blen_c)+3
                    cut_off=(blen_c/2) if k2%2==1 else 0
                    for j in range(-1,n_c2+1):
                        cv2=cut_st2+cut_off+j*blen_c
                        if not slash:  # \ stripe, cut at x+y=cv2
                            xp1=(cv2-c1k)/2; yp1=(cv2+c1k)/2
                            xp2=(cv2-c2k)/2; yp2=(cv2+c2k)/2
                        else:           # / stripe, cut at y-x=cv2
                            xp1=(c1k-cv2)/2; yp1=(c1k+cv2)/2
                            xp2=(c2k-cv2)/2; yp2=(c2k+cv2)/2
                        seg=_lc(xp1,yp1,xp2,yp2)
                        if seg: c.create_line(seg[0],seg[1],seg[2],seg[3],fill=GRN,width=2)
            c.create_rectangle(deck_x0,deck_y0,deck_x1,deck_y1, fill="", outline=O, width=2)
            dir_lbl = "45° Right (/)" if slash else "45° Left (\\)"
            c.create_text(deck_x0, 10, fill="#444", font=("Segoe UI",9,"bold"), anchor="w",
                          text=f'Boards {bwid}"  |  Gaps {gap}"  |  {dir_lbl}')
            diag_ft = _dm.sqrt(dl**2+dw**2)
            c.create_text(deck_x1, 24, text=f"Diagonal: {diag_ft:.2f} ft",
                          fill=GRN, font=("Segoe UI",9,"bold"), anchor="e")
            ax=deck_x0-22; mid_y=(deck_y0+deck_y1)/2
            c.create_line(ax,deck_y0+2,ax,deck_y1-2, fill=DIM, width=1, arrow="both")
            c.create_text(ax-6,mid_y-8, text="Width", fill=DIM, font=("Segoe UI",9,"bold"), anchor="e")
            c.create_text(ax-6,mid_y+8, text=f"{dw} ft", fill=DIM, font=("Segoe UI",9), anchor="e")
            r1=deck_y1+22; r2=deck_y1+46; r3=deck_y1+70
            def ar(yl,x0a,x1a,lbl,col,dsh=False):
                if x1a-x0a<6: return
                c.create_line(x0a+2,yl,x1a-2,yl,fill=col,width=2 if not dsh else 1,
                              arrow="both",dash=(4,3) if dsh else ())
                c.create_text((x0a+x1a)/2,yl-10,text=lbl,fill=col,
                              font=("Segoe UI",9,"bold" if not dsh else "normal"))
            ar(r1,deck_x0,deck_x0+min(diag_ft*sc_x,DW),f"Diagonal: {diag_ft:.2f} ft",GRN)
            ar(r2,deck_x0,deck_x0+min(blen*sc_x,DW/2),f"Board: {blen} ft",GRN,dsh=True)
            ar(r3,deck_x0,deck_x1,f"Deck length: {dl} ft",DIM)
            return

        # ── Board rows: alternating half-board stagger (across width) ──
        y=deck_y0; row=0
        while y < deck_y1 and row < 80:
            bh=max(3, bwid/12*sc_y); ry1=min(y+bh, deck_y1)
            offset_px=(blen_px/2) if row%2==1 else 0.0
            j=0
            while True:
                bx0=deck_x0 - offset_px + j*blen_px
                if bx0>=deck_x1: break
                dx0=max(deck_x0,bx0); dx1=min(deck_x1,bx0+blen_px)
                if dx0<dx1:
                    c.create_rectangle(dx0,y,dx1,ry1,fill=F,outline=O,width=1)
                if deck_x0+1 < bx0 < deck_x1-1:
                    c.create_line(bx0,y,bx0,ry1,fill=GRN,width=2)
                j+=1
            y+=cov_px; row+=1

        # ── Dashed joists ─────────────────────────────────────────
        x=deck_x0
        while x<=deck_x1:
            c.create_line(x,deck_y0,x,deck_y1,fill="#B0B8C8",width=1,dash=(4,4))
            x+=max(joist_px,1)

        # ── Width arrow on left side ──────────────────────────────
        ax=deck_x0-22
        c.create_line(ax,deck_y0+2,ax,deck_y1-2,fill=DIM,width=1,arrow="both")
        # Two-line label: "Width" above, value below, right-aligned to ax-6
        mid_y=(deck_y0+deck_y1)/2
        c.create_text(ax-6,mid_y-8,text="Width",fill=DIM,font=("Segoe UI",9,"bold"),anchor="e")
        c.create_text(ax-6,mid_y+8,text=f"{dw} ft",fill=DIM,font=("Segoe UI",9),anchor="e")

        # ── Below-deck: 3 annotation rows ────────────────────────
        # Each row: arrow line then label centered ABOVE the line
        # Row spacing: 24px
        def ann_row(y_line, x0, x1, label, color, dashed=False):
            """Arrow with label centered above it, fully within canvas."""
            if x1-x0 < 6: return
            dash_arg = (4,3) if dashed else ()
            c.create_line(x0+2,y_line,x1-2,y_line,
                          fill=color,width=2 if not dashed else 1,
                          arrow="both",dash=dash_arg)
            c.create_text((x0+x1)/2, y_line-10,
                          text=label,fill=color,
                          font=("Segoe UI",9,"bold" if not dashed else "normal"))

        r1=deck_y1+22; r2=deck_y1+46; r3=deck_y1+70

        # Row 1: board length (green solid)
        blen_draw=min(blen_px, DW)
        ann_row(r1, deck_x0, deck_x0+blen_draw,
                f"Board length: {blen} ft", GRN)

        # Row 2: stagger offset (green dashed)
        stagger_draw=min(blen_px/2, DW)
        ann_row(r2, deck_x0, deck_x0+stagger_draw,
                f"\u00bd stagger: {blen/2:.2f} ft", GRN, dashed=True)

        # Row 3: deck length (navy)
        ann_row(r3, deck_x0, deck_x1,
                f"Deck length: {dl} ft", DIM)

        # ── Legend in right margin at r1 and r2 rows ────────────
        lgx = deck_x1+10   # start of right margin area
        c.create_line(lgx,r1,lgx+16,r1,fill=GRN,width=2)
        c.create_text(lgx+19,r1,text="= board joint",
                      fill=GRN,font=("Segoe UI",9),anchor="w")
        c.create_line(lgx,r2,lgx+16,r2,fill="#B0B8C8",width=1,dash=(4,4))
        c.create_text(lgx+19,r2,text="= joist",
                      fill="#888",font=("Segoe UI",9),anchor="w")

    # ── LUMBER ────────────────────────────────────────────
    def _on_lb_cfg(self, event):
        self._lb_cv_w = event.width; self._draw_lb_diagram()

    def _draw_lb_diagram(self):
        c = self._lb_cv; c.delete("all")
        W = getattr(self,"_lb_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_lb_diag",None)
        if not d: self._dph(c,W,H); return
        t=d["t"]; w=d["w"]; l=d["l"]
        F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; OFF=16; PAD=50
        bw=min(W-2*PAD-OFF,340); bh=min(H-60-OFF,50)
        x0=(W-bw-OFF)//2; y0=(H-bh-OFF)//2
        c.create_rectangle(x0,y0+OFF,x0+bw,y0+bh+OFF,fill=F,outline=O,width=2)
        c.create_polygon([x0,y0+OFF,x0+OFF,y0,x0+bw+OFF,y0,x0+bw,y0+OFF],fill=INPUT_BG,outline=O,width=2)
        c.create_polygon([x0+bw,y0+OFF,x0+bw+OFF,y0,x0+bw+OFF,y0+bh,x0+bw,y0+bh+OFF],fill="#C8DCF0",outline=O,width=2)
        self._ha(c,x0,y0+bh+OFF+12,x0+bw,DIM,f"L = {l} ft",above=False)
        self._va(c,x0-12,y0+OFF,y0+bh+OFF,DIM,f'W = {w}"',right=False)
        c.create_text(x0+bw+OFF+4,y0+bh//2,text=f'T={t}"',fill=DIM,font=("Segoe UI",8),anchor="w")

    # ── ROOFING ───────────────────────────────────────────
    def _on_rf_cfg(self, event):
        self._rf_cv_w = event.width; self._draw_rf_diagram()

    def _draw_rf_diagram(self):
        c = self._rf_cv; c.delete("all")
        W = getattr(self,"_rf_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_rf_diag",None)
        if not d: self._dph(c,W,H); return
        W_ft=d["W"]; pitch=d["pitch"]; raft=d["raft"]; ang=d["ang"]
        F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; PAD=60
        span_px=W-2*PAD; rise_ft=(W_ft/2)*(pitch/12)
        sc=min(span_px/(W_ft or 1),(H-80)/(rise_ft or 1))
        pw=W_ft*sc; ph=rise_ft*sc; bx=W//2; ey=H-30; ty=ey-ph
        lx=bx-pw/2; rx=bx+pw/2
        c.create_polygon([lx,ey,rx,ey,bx,ty],fill=F,outline=O,width=2)
        c.create_line(bx,ty,bx,ey,fill="#AAA",width=1,dash=(4,3))
        self._ha(c,lx,ey+12,rx,DIM,f"Width: {W_ft} ft",above=False)
        c.create_text(bx+8,ty+(ey-ty)*0.4,text=f"{pitch}:12",fill=O,font=("Segoe UI",9,"bold"),anchor="w")
        # Rafter label: offset perpendicular (outward/downward-left) from the slope
        # Slope vector: (bx-lx, ty-ey). Perpendicular (left/outward): (ty-ey, -(bx-lx))
        _dx=bx-lx; _dy=ty-ey; _mag=max(1,(_dx**2+_dy**2)**0.5)
        _px=_dy/_mag; _py=-_dx/_mag   # unit perpendicular pointing left of slope
        _mx=(lx+bx)/2; _my=(ey+ty)/2
        _offset=18                     # pixels off the line
        c.create_text(_mx+_px*_offset, _my+_py*_offset,
                      text=f"rafter\n{raft:.1f} ft",fill=DIM,font=("Segoe UI",8),
                      justify="center")
        c.create_text(bx+6,ey-14,text=f"{ang:.1f}°",fill=DIM,font=("Segoe UI",8),anchor="w")

    # ── STAIRS ────────────────────────────────────────────
    def _on_st_cfg(self, event):
        self._st_cv_w = event.width; self._draw_st_diagram()

    def _draw_st_diagram(self):
        """Clean 4-panel stairs: navy header bars, labels in dedicated zones."""
        import math as _m
        c = self._st_cv; c.delete("all")
        W = getattr(self,"_st_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_st_diag",None)
        if not d: self._dph(c,W,H); return
        n_ris=d["n_ris"]; act_r=d["act_r"]; tread=d["tread"]
        run=d.get("run",tread); nose=d.get("nose",0)
        t_run=d["t_run"]; total=d["total"]
        s_len=_m.sqrt(total**2+t_run**2)/12
        angle=_m.degrees(_m.atan(total/t_run)) if t_run else 90
        step_hyp=_m.sqrt(act_r**2+run**2)
        MX=W//2; MY=H//2
        F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; ST="#E8A020"; NF="#2F5496"
        HDR=18   # header bar height
        PAD=12   # inner padding

        # ── Navy header bars with white labels ────────────────────
        for x0,y0,x1,lbl in [
            (0,0,MX,       "Overview"),
            (MX,0,W,        "Step Detail"),
            (0,MY,MX,       "Stringer Cut"),
            (MX,MY,W,       "Dimensions")]:
            c.create_rectangle(x0,y0,x1,y0+HDR,fill=NAV_BG,outline="")
            c.create_text((x0+x1)//2,y0+HDR//2,text=lbl,
                          fill="white",font=("Segoe UI",8,"bold"))
        # Panel border lines
        c.create_line(MX,0,MX,H,fill=BORDER,width=1)
        c.create_line(0,MY,W,MY,fill=BORDER,width=1)

        # ── Shorthand helpers ─────────────────────────────────────
        def step(cx,cy, rw,rh,npx,riw, n_draw):
            """Draw n_draw steps from bottom-left corner (cx,cy)."""
            for i in range(n_draw):
                bx=cx+i*rw; by=cy-i*rh
                c.create_rectangle(bx,by-rh,bx+rw,by,fill=F,outline=O,width=2)
                c.create_rectangle(bx+rw,by-rh,bx+rw+riw,by,
                                   fill="#4A90D9",outline=NF,width=2)
                if i>0 and npx>0:
                    th=max(4,min(8,rh*0.18))
                    c.create_rectangle(bx-npx,by-rh,bx,by-rh+th,
                                       fill=NF,outline=O,width=1)

        # ═══ P1 OVERVIEW (0,HDR → MX,MY) ════════════════════════
        # Zones: left 38px=rise label, bottom 22px=run label, rest=staircase
        p1x=38; p1y=HDR+PAD; p1w=MX-p1x-PAD; p1h=MY-p1y-22
        n1=min(n_ris,7)
        sc1=min(p1w/(run*n1 or 1), p1h/(act_r*n1 or 1))*0.86
        rw1=run*sc1; rh1=act_r*sc1; npx1=nose*sc1; riw1=max(2,rw1*0.07)
        tw1=rw1*n1; th1=rh1*n1
        # Anchor steps at bottom-left of stair zone
        # Centre staircase in draw zone (p1x to MX-PAD)
        sx1=int(p1x + max(0,(MX-PAD-p1x-tw1)/2)); sy1=MY-22
        # Stringer (drawn first, behind steps)
        c.create_line(sx1,sy1,sx1+tw1,sy1-th1,fill=ST,width=2)
        step(sx1,sy1,rw1,rh1,npx1,riw1,n1)
        # Rise arrow — follows sx1 so it stays left of the staircase
        self._va(c,sx1-14,sy1-th1,sy1,DIM,inches_to_feet(total),right=False)
        # Run arrow — bottom zone
        self._ha(c,sx1,MY-22,sx1+tw1,DIM,inches_to_feet(t_run),above=False)
        # Stringer label — in the EMPTY space above-left of steps
        slx=sx1+tw1//2; sly=sy1-th1-10
        # Make sure it's inside the panel and not on the steps
        slx=max(p1x+4, min(slx, MX-60))
        sly=max(HDR+PAD+4, sly)
        c.create_text(slx,sly,text=f"stringer  {s_len:.2f} ft",
                      fill=ST,font=("Segoe UI",8),anchor="w")
        # Angle label — bottom-right of staircase, in run-label zone
        c.create_text(sx1+tw1+2,MY-12,text=f"{angle:.1f}°",
                      fill=DIM,font=("Segoe UI",8),anchor="w")

        # ═══ P2 STEP DETAIL (MX,HDR → W,MY) ════════════════════
        # Reserve: top=28 tread label, bottom=40 run arrow+text, right=70 rise
        # sy2=MY-40 leaves 40px below steps for the arrow (at +14) and text (at +23)
        p2x=MX+PAD+14; p2y=HDR+28; p2w=MX-PAD-14-70; p2h=MY-HDR-28-40
        sc2=min(p2w/(run*2 or 1), p2h/(act_r*2 or 1))*0.82
        rw2=run*sc2; rh2=act_r*sc2; npx2=nose*sc2; riw2=max(4,min(10,rw2*0.12))
        # Centre the 2 steps within the available p2w
        sx2=int(p2x + max(0,(p2w - 2*rw2 - riw2)/2)); sy2=MY-40
        step(sx2,sy2,rw2,rh2,npx2,riw2,2)
        # Tread label — top zone (above first step)
        c.create_text((sx2-npx2+sx2+rw2)//2, HDR+14,
                      text=f"tread  {inches_to_ruler(tread)}",
                      fill="#555",font=("Segoe UI",8))
        # Run arrow — BELOW the step bottom (sy2+14), text at sy2+23, well inside panel
        self._ha(c,sx2,sy2+14,sx2+rw2,DIM,f'run  {inches_to_ruler(run)}',above=False)
        # Rise arrow — right zone
        self._va(c,sx2+rw2+riw2+8,sy2-rh2,sy2,DIM,f'rise  {inches_to_ruler(act_r)}')
        # Nose label — just above the nosing strip on step 2, to the LEFT
        if npx2>3 and n_ris>1:
            nx2=sx2+rw2; ny2=sy2-2*rh2
            c.create_text(nx2-npx2-2,ny2-4,
                          text=f'nose\n{inches_to_ruler(nose)}',
                          fill=NF,font=("Segoe UI",7),anchor="e",justify="right")

        # ═══ P3 STRINGER CUT (0,MY+HDR → MX,H) ═════════════════
        # Center one step, show stringer line + angles
        p3x=PAD+20; p3y=MY+HDR+PAD; p3w=MX-PAD-20-PAD; p3h=H-p3y-PAD
        sc3=min(p3w/(run or 1), p3h/(act_r or 1))*0.62
        rw3=run*sc3; rh3=act_r*sc3; riw3=max(3,min(8,rw3*0.1))
        # Center the step in P3
        sx3=(MX-rw3-riw3)//2; sy3=MY+HDR+PAD+rh3+(p3h-rh3)//2
        sy3=min(sy3, H-PAD)
        step(sx3,sy3,rw3,rh3,0,riw3,1)
        # Stringer line — extend beyond step corners
        ext3=max(rw3,rh3)*0.55
        lx3=sx3-ext3*(run/step_hyp); ly3=sy3+ext3*(act_r/step_hyp)
        rx3=sx3+rw3+riw3+ext3*(run/step_hyp); ry3=sy3-rh3-ext3*(act_r/step_hyp)
        c.create_line(lx3,ly3,rx3,ry3,fill=ST,width=2)
        # Bottom angle — label to the right of the step bottom, outside the rectangle
        c.create_text(sx3+rw3+riw3+8,sy3+4,
                      text=f"{angle:.1f}°",fill=DIM,font=("Segoe UI",10,"bold"),anchor="w")
        # Top angle — above top-right corner
        c.create_text(sx3+rw3+riw3+8,sy3-rh3-8,
                      text=f"{90-angle:.1f}°",fill=DIM,font=("Segoe UI",9),anchor="w")
        # Step hyp label — placed in bottom-left of P3 panel (safe fixed position)
        _label_y = min(H-PAD-4, sy3+rh3//2+14)
        _label_y = max(MY+HDR+PAD+4, _label_y)
        c.create_text(PAD+24, _label_y,
                      text=f"step  {inches_to_ruler(step_hyp)}",
                      fill=ST, font=("Segoe UI",9,"bold"), anchor="w")


        # ═══ P4 DIMENSIONS (MX,MY+HDR → W,H) ═══════════════════
        # Reserve: top=38 trd+nose labels, bottom=22 run, right=72 rise, left=18 nose space
        p4x=MX+PAD+18; p4y=MY+HDR+38; p4w=MX-PAD-18-72; p4h=H-p4y-22
        sc4=min(p4w/(run or 1), p4h/(act_r or 1))*0.80
        rw4=run*sc4; rh4=act_r*sc4; npx4=nose*sc4; riw4=max(3,min(9,rw4*0.1))
        # Centre step horizontally within p4w, vertically in zone
        sx4=int(p4x + max(0,(p4w - rw4 - riw4)/2))
        _zone_top=MY+HDR+38; _zone_bot=H-32
        sy4=(_zone_top+_zone_bot)//2 + int(rh4//2)
        step(sx4,sy4,rw4,rh4,npx4,riw4,1)
        # Tread board arrow — top row (row 1)
        t_lbl_y=MY+HDR+12
        self._ha(c,max(MX+8,int(sx4-npx4)),t_lbl_y,sx4+rw4,DIM,f'trd  {inches_to_ruler(tread)}')
        # Nose arrow — top row (row 2, 14px below tread)
        if npx4>3:
            _nose_x0=max(MX+8,int(sx4-npx4))
        self._ha(c,_nose_x0,t_lbl_y+14,sx4,NF,f'nose  {inches_to_ruler(nose)}')
        # Run arrow — bottom zone
        self._ha(c,sx4,H-20,sx4+rw4,DIM,f'run  {inches_to_ruler(run)}',above=False)
        # Rise arrow — right zone
        self._va(c,sx4+rw4+riw4+10,sy4-rh4,sy4,DIM,f'rise  {inches_to_ruler(act_r)}')

    # ── VOLUME ────────────────────────────────────────────
    def _on_vol_cfg(self, event):
        self._vol_cv_w = event.width; self._draw_vol_diagram()

    def _draw_vol_diagram(self):
        c = self._vol_cv; c.delete("all")
        W = getattr(self,"_vol_cv_w",0) or c.winfo_width() or 500
        H = int(c.cget("height"))
        d = getattr(self,"_vol_diag",None)
        if not d: self._dph(c,W,H); return
        shape=d["shape"]; MX=W//2; MY=H//2; F=RES_BG; O="#1565C0"; DIM=DIAGRAM_DIM; OFF=16

        if shape == "Rectangular Box":
            L=d["L"]; Wd=d["W"]; Ht=d["H"]
            sc=min((W-100)/(L or 1),(H-80)/(Ht or 1))*0.65
            pw=L*sc; ph=Ht*sc; x0=MX-pw/2-OFF//2; y0=MY-ph/2
            c.create_rectangle(x0,y0+OFF,x0+pw,y0+ph+OFF,fill=F,outline=O,width=2)
            c.create_polygon([x0,y0+OFF,x0+OFF,y0,x0+pw+OFF,y0,x0+pw,y0+OFF],fill=INPUT_BG,outline=O,width=2)
            c.create_polygon([x0+pw,y0+OFF,x0+pw+OFF,y0,x0+pw+OFF,y0+ph,x0+pw,y0+ph+OFF],fill="#C8DCF0",outline=O,width=2)
            self._ha(c,x0,y0+ph+OFF+12,x0+pw,DIM,f"L={L} ft",above=False)
            self._va(c,x0-12,y0+OFF,y0+ph+OFF,DIM,f"H={Ht} ft",right=False)
            c.create_text(x0+pw+OFF+4,y0+ph//2,text=f"W={Wd} ft",fill=DIM,font=("Segoe UI",8),anchor="w")
        elif shape == "Cylinder":
            r=d["r"]; h=d["h"]
            rx=min((W-100)/2,65); ry=rx*0.35
            sc=min((H-80)/(h or 1),1); ph=min(h*sc*10,H-70)
            c.create_oval(MX-rx,MY+ph/2-ry,MX+rx,MY+ph/2+ry,fill=F,outline=O,width=2)
            c.create_rectangle(MX-rx,MY-ph/2,MX+rx,MY+ph/2,fill=F,outline="")
            c.create_line(MX-rx,MY-ph/2,MX-rx,MY+ph/2,fill=O,width=2)
            c.create_line(MX+rx,MY-ph/2,MX+rx,MY+ph/2,fill=O,width=2)
            c.create_oval(MX-rx,MY-ph/2-ry,MX+rx,MY-ph/2+ry,fill=F,outline=O,width=2)
            self._ha(c,MX,MY-ph/2-ry-14,MX+rx,DIM,f"r={r} ft")
            self._va(c,MX+rx+12,MY-ph/2,MY+ph/2,DIM,f"h={h} ft")
        elif shape == "Cone":
            r=d["r"]; h=d["h"]; sl=d["sl"]
            rx=min((W-100)/2,70); ry=rx*0.35
            sc=min((H-70)/(h or 1),1); ph=min(h*sc*10,H-65)
            bx=MX; by=MY+ph/2
            c.create_oval(bx-rx,by-ry,bx+rx,by+ry,fill=F,outline=O,width=2)
            c.create_polygon([bx-rx,by,bx,by-ph,bx+rx,by],fill=F,outline=O,width=2)
            self._ha(c,bx,by+ry+12,bx+rx,DIM,f"r={r} ft",above=False)
            self._va(c,bx+rx+12,by-ph,by,DIM,f"h={h} ft")
        elif shape == "Sphere":
            r=d["r"]; pr=min((W-80)/2,(H-60)/2)*0.8
            c.create_oval(MX-pr,MY-pr,MX+pr,MY+pr,fill=F,outline=O,width=2)
            c.create_arc(MX-pr,MY-pr*0.35,MX+pr,MY+pr*0.35,start=0,extent=180,outline="#88AABB",style="arc",width=1,dash=(4,3))
            c.create_arc(MX-pr,MY-pr*0.35,MX+pr,MY+pr*0.35,start=180,extent=180,outline="#88AABB",style="arc",width=1)
            c.create_line(MX,MY,MX+pr,MY,fill=DIM,width=1)
            c.create_oval(MX-3,MY-3,MX+3,MY+3,fill=DIM,outline=DIM)
            c.create_text(MX+pr/2,MY-12,text=f"r={r} ft",fill=DIM,font=("Segoe UI",9))
        elif shape == "Triangular Prism":
            b=d["b"]; h=d["h"]; l=d["l"]
            sc=min((W-100)/(b or 1),(H-80)/(h or 1))*0.5
            pb=b*sc; ph=h*sc; ox=OFF; oy=-OFF; bx=MX; by=MY+ph/2
            pts=[bx-pb/2,by,bx+pb/2,by,bx,by-ph]
            pts2=[pts[0]+ox,pts[1]+oy,pts[2]+ox,pts[3]+oy,pts[4]+ox,pts[5]+oy]
            c.create_polygon(pts2,fill=INPUT_BG,outline=O,width=1)
            for j in range(0,6,2):
                c.create_line(pts[j],pts[j+1],pts2[j],pts2[j+1],fill=O,width=1)
            c.create_polygon(pts,fill=F,outline=O,width=2)
            self._ha(c,bx-pb/2,by+12,bx+pb/2,DIM,f"b={b} ft",above=False)
            self._va(c,bx+pb/2+12,by-ph,by,DIM,f"h={h} ft")
            c.create_text(bx+pb/2+ox+4,by-ph//2+oy,text=f"l={l} ft",fill=DIM,font=("Segoe UI",8),anchor="w")



# ─────────────────────────────────────────────────────────
# FINANCE CALCULATORS TAB
# ─────────────────────────────────────────────────────────

# 7 NEW CONSTRUCTION CALCULATORS  (injected after _draw_vl_diagram)
# Corner Angle · Crown Molding · Diagonal · Miter Joint
# Parquet Floor · Ramp · Slope
# ─────────────────────────────────────────────────────────────────────────────
    def _build_corner_angle(self):
        tab = self._all_frames["Corner Angle"]
        inner, res = self._two_col(tab)
        self._ca_corner = self._le(inner, 'Corner Angle (°)', '90')
        calc_button(tab, 'Calculate →', self._calc_corner_angle,
                    clear_cmd=self._clear_corner_angle,
                    sample_cmd=self._sample_corner_angle)
        self._ca_half_v = tk.StringVar(value='—')
        self._ca_cut_v  = tk.StringVar(value='—')
        self._rr(res, 'Half Angle (°)',  self._ca_half_v, color=ACCENT)
        self._rr(res, 'Cut Angle (°)',   self._ca_cut_v)

    def _calc_corner_angle(self):
        try:
            import math as _m
            ca = float(self._ca_corner.get())
            if not (0 < ca < 360): raise ValueError('angle must be 0-360')
            half = ca / 2
            cut  = (180 - ca) / 2
            self._ca_half_v.set(f'{half:.2f}°')
            self._ca_cut_v.set(f'{cut:.2f}°')
            self._ca_diag = dict(ca=ca, half=half, cut=cut)
            self._draw_ca_diagram()
        except Exception as e:
            self._ca_half_v.set(f'Error: {e}')

    def _clear_corner_angle(self):
        self._ca_corner.set('')
        self._ca_half_v.set('—'); self._ca_cut_v.set('—')
        self._ca_diag = None
        if hasattr(self,'_ca_cv'): self._ca_cv.delete('all')

    def _sample_corner_angle(self):
        self._ca_corner.set('90')

    def _on_ca_cfg(self, event):
        self._ca_cv_w = event.width; self._draw_ca_diagram()

    def _draw_ca_diagram(self):
        import math as _m
        c=self._ca_cv; c.delete('all')
        W=getattr(self,'_ca_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_ca_diag',None)
        if not d: self._dph(c,W,H); return
        ca=d['ca']; half=d['half']; cut=d['cut']
        # Corner at bottom-left; one arm goes RIGHT, other goes up at ca°
        cx=int(W*0.22); cy=H-36; arm=int(min(W-cx-30, H-cy-10+cy-30)*0.88)
        # Filled sector (material in the corner)
        pts=[cx,cy]
        for i in range(31):
            a=_m.radians(ca*i/30)
            pts+=[int(cx+arm*_m.cos(a)), int(cy-arm*_m.sin(a))]
        pts+=[cx,cy]
        c.create_polygon(pts,fill=INPUT_BG,outline='',width=0)
        # Wall lines
        c.create_line(cx,cy,cx+arm,cy,fill=NAV_BG,width=3)
        ex2=int(cx+arm*_m.cos(_m.radians(ca))); ey2=int(cy-arm*_m.sin(_m.radians(ca)))
        c.create_line(cx,cy,ex2,ey2,fill=NAV_BG,width=3)
        c.create_rectangle(cx-1,cy-1,cx+1,cy+1,fill=NAV_BG,outline='')  # corner dot
        # Corner angle arc (outer)
        r_big=min(arm-6,int(arm*0.75))
        c.create_arc(cx-r_big,cy-r_big,cx+r_big,cy+r_big,
                     start=0,extent=ca,style='arc',outline=ACCENT,width=2)
        mid_ca=_m.radians(ca/2)
        lx=int(cx+(r_big+16)*_m.cos(mid_ca)); ly=int(cy-(r_big+16)*_m.sin(mid_ca))
        c.create_text(lx,ly,text=f'{ca:.1f}°',fill=ACCENT,font=('Segoe UI',10,'bold'))
        # Bisector dashed line
        r_bis=int(arm*0.88)
        bx=int(cx+r_bis*_m.cos(mid_ca)); by=int(cy-r_bis*_m.sin(mid_ca))
        c.create_line(cx,cy,bx,by,fill=NAV_BG,width=1,dash=(4,3))
        # Half angle arc (inner)
        r_sm=int(r_big*0.42)
        c.create_arc(cx-r_sm,cy-r_sm,cx+r_sm,cy+r_sm,
                     start=0,extent=half,style='arc',outline=NAV_BG,width=1)
        hx=int(cx+(r_sm+12)*_m.cos(_m.radians(half/2)))
        hy=int(cy-(r_sm+12)*_m.sin(_m.radians(half/2)))
        c.create_text(hx,hy,text=f'{half:.1f}°',fill=NAV_BG,font=('Segoe UI',9))
        # Bottom labels
        c.create_text(W//2,H-14,
                      text=f'Corner: {ca:.1f}°   Half: {half:.1f}°   Cut: {cut:.1f}°',
                      fill=TEXT,font=('Segoe UI',9,'bold'))

    def _build_diagonal(self):
        tab = self._all_frames["Diagonal"]
        inner, res = self._two_col(tab)
        self._dg_w   = self._le(inner, 'Width (ft)',  '12')
        self._dg_l   = self._le(inner, 'Length (ft)', '9')
        calc_button(tab, 'Calculate →', self._calc_diagonal,
                    clear_cmd=self._clear_diagonal,
                    sample_cmd=self._sample_diagonal)
        self._dg_diag_v = tk.StringVar(value='—')
        self._dg_diag_in= tk.StringVar(value='—')
        self._rr(res, 'Diagonal (ft–in)', self._dg_diag_v, color=ACCENT)
        self._rr(res, 'Diagonal (in)',    self._dg_diag_in)

    def _calc_diagonal(self):
        try:
            import math as _m
            w = float(self._dg_w.get())*12
            l = float(self._dg_l.get())*12
            d = _m.sqrt(w*w+l*l)
            self._dg_diag_v.set(inches_to_feet(d))
            self._dg_diag_in.set(f'{d:.4f}"')
            self._dg_diag = dict(w=w,l=l,d=d)
            self._draw_dg_diagram()
        except Exception as e:
            self._dg_diag_v.set(f'Error: {e}')

    def _clear_diagonal(self):
        self._dg_w.set(''); self._dg_l.set('')
        self._dg_diag_v.set('—'); self._dg_diag_in.set('—')
        self._dg_diag=None
        if hasattr(self,'_dg_cv'): self._dg_cv.delete('all')

    def _sample_diagonal(self):
        self._dg_w.set('12'); self._dg_l.set('9')

    def _on_dg_cfg(self,event):
        self._dg_cv_w=event.width; self._draw_dg_diagram()

    def _draw_dg_diagram(self):
        import math as _m
        c=self._dg_cv; c.delete('all')
        W=getattr(self,'_dg_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_dg_diag',None)
        if not d: self._dph(c,W,H); return
        w=d['w']; l=d['l']; diag=d['d']
        DIM=NAV_BG
        PAD_T=24; PAD_B=32; PAD_L=72; PAD_R=24
        avw=W-PAD_L-PAD_R; avh=H-PAD_T-PAD_B
        scale=min(avw/(w or 1), avh/(l or 1))*0.85
        pw=int(w*scale); pl=int(l*scale)
        x0=PAD_L+(avw-pw)//2; y0=H-PAD_B
        x1=x0+pw; y1=y0-pl
        # Right angle at bottom-left
        c.create_polygon(x0,y0, x0,y1, x1,y0, fill=INPUT_BG,outline=ACCENT,width=2)
        c.create_line(x0,y1, x1,y0, fill=ACCENT,width=2)
        self._ha(c,x0,y0+20,x1,DIM,inches_to_feet(w),above=False)
        self._va(c,x0-22,y1,y0,DIM,inches_to_feet(l),right=False)
        # Diagonal label — offset 28px perpendicular to hypotenuse (away from line)
        mx=(x0+x1)//2; my=(y0+y1)//2
        hyp_len=_m.sqrt(pw*pw+pl*pl) or 1
        # Perpendicular pointing to lower-right (outside triangle)
        px_n=pl/hyp_len; py_n=pw/hyp_len
        c.create_text(int(mx+px_n*28),int(my+py_n*28),
                      text=inches_to_feet(diag),
                      fill=ACCENT,font=('Segoe UI',10,'bold'),anchor='center')

    def _build_slope(self):
        tab = self._all_frames["Slope"]
        inner, res = self._two_col(tab)
        self._sl_run  = self._le(inner,'Horizontal Run (ft)','10')
        self._sl_rise = self._le(inner,'Vertical Rise (ft)', '5')
        calc_button(tab,'Calculate →',self._calc_slope,
                    clear_cmd=self._clear_slope,sample_cmd=self._sample_slope)
        self._sl_ang_v = tk.StringVar(value='—')
        self._sl_pct_v = tk.StringVar(value='—')
        self._sl_i12_v = tk.StringVar(value='—')
        self._rr(res,'Slope Angle (°)',  self._sl_ang_v,color=ACCENT)
        self._rr(res,'Slope (%)',        self._sl_pct_v)
        self._rr(res,'Rise per 12" run', self._sl_i12_v)

    def _calc_slope(self):
        try:
            import math as _m
            run  = float(self._sl_run.get())*12
            rise = float(self._sl_rise.get())*12
            if run<=0: raise ValueError('run must be > 0')
            ang  = _m.degrees(_m.atan2(rise,run))
            pct  = rise/run*100
            i12  = rise*12/run
            self._sl_ang_v.set(f'{ang:.2f}°')
            self._sl_pct_v.set(f'{pct:.1f}%')
            self._sl_i12_v.set(f'{i12:.3f}"')
            self._sl_diag=dict(run=run,rise=rise,ang=ang,pct=pct)
            self._draw_sl_diagram()
        except Exception as e:
            self._sl_ang_v.set(f'Error: {e}')

    def _clear_slope(self):
        self._sl_run.set(''); self._sl_rise.set('')
        for v in [self._sl_ang_v,self._sl_pct_v,self._sl_i12_v]: v.set('—')
        self._sl_diag=None
        if hasattr(self,'_sl_cv'): self._sl_cv.delete('all')

    def _sample_slope(self):
        self._sl_run.set('10'); self._sl_rise.set('5')

    def _on_sl_cfg(self,event):
        self._sl_cv_w=event.width; self._draw_sl_diagram()

    def _draw_sl_diagram(self):
        import math as _m
        c=self._sl_cv; c.delete('all')
        W=getattr(self,'_sl_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_sl_diag',None)
        if not d: self._dph(c,W,H); return
        run=d['run']; rise=d['rise']; ang=d['ang']; pct=d['pct']
        DIM=NAV_BG
        PAD_T=16; PAD_B=38; PAD_L=20; PAD_R=70
        avw=W-PAD_L-PAD_R; avh=H-PAD_T-PAD_B
        scale=min(avw/(run or 1), avh/(rise or 1))*0.84
        pw=int(run*scale); ph=int(rise*scale)
        x0=PAD_L+(avw-pw)//2; x1=x0+pw
        y_bot=H-PAD_B; y_top=y_bot-ph
        # Rising slope: lower-left to upper-right — right angle at lower-right
        c.create_polygon(x0,y_bot, x1,y_bot, x1,y_top,
                         fill=INPUT_BG,outline=ACCENT,width=2)
        c.create_line(x0,y_bot, x1,y_top, fill=ACCENT,width=2)
        # Run at BOTTOM, Rise on RIGHT
        self._ha(c,x0,y_bot+22,x1,DIM,inches_to_feet(run),above=False)
        self._va(c,x1+18,y_top,y_bot,DIM,inches_to_feet(rise),right=True)
        # Angle arc at lower-left corner
        ar=int(min(pw*0.20,34))
        c.create_arc(x0-ar,y_bot-ar,x0+ar,y_bot+ar,
                     start=0,extent=ang,style='arc',outline=DIM,width=2)
        lx=int(x0+(ar+28)*_m.cos(_m.radians(ang/2)))
        ly=int(y_bot-(ar+18)*_m.sin(_m.radians(ang/2)))
        c.create_text(lx,ly,text=f'{ang:.1f}°  {pct:.0f}%',
                      fill=DIM,font=('Segoe UI',9,'bold'),anchor='w')

    def _build_ramp(self):
        tab=self._all_frames["Ramp"]
        inner,res=self._two_col(tab)
        self._rp_len = self._le(inner,'Ramp Length (ft)','10')
        self._rp_ht  = self._le(inner,'Ramp Height (ft)','1')
        self._rp_dim = self._le(inner,'Material Thickness (in)','1.5')
        calc_button(tab,'Calculate →',self._calc_ramp,
                    clear_cmd=self._clear_ramp,sample_cmd=self._sample_ramp)
        self._rp_diag_v=tk.StringVar(value='—')
        self._rp_ang1_v=tk.StringVar(value='—')
        self._rp_len1_v=tk.StringVar(value='—')
        self._rp_ang2_v=tk.StringVar(value='—')
        self._rp_len2_v=tk.StringVar(value='—')
        self._rr(res,'Diagonal Length',  self._rp_diag_v,color=ACCENT)
        self._rr(res,'Cut Angle 1 (°)',  self._rp_ang1_v)
        self._rr(res,'Cut Length 1',     self._rp_len1_v)
        self._rr(res,'Cut Angle 2 (°)',  self._rp_ang2_v)
        self._rr(res,'Cut Length 2',     self._rp_len2_v)

    def _calc_ramp(self):
        try:
            import math as _m
            length=float(self._rp_len.get())*12
            height=float(self._rp_ht.get())*12
            dim   =float(self._rp_dim.get())
            if length<=0: raise ValueError('length must be > 0')
            diag  =_m.sqrt(length**2+height**2)
            ang   =_m.degrees(_m.atan2(height,length))
            cut1  =dim/_m.cos(_m.radians(ang))
            cut2  =dim/_m.sin(_m.radians(ang)) if ang>0.1 else 0
            ang2  =90-ang
            self._rp_diag_v.set(inches_to_feet(diag))
            self._rp_ang1_v.set(f'{ang:.2f}°')
            self._rp_len1_v.set(inches_to_ruler(cut1))
            self._rp_ang2_v.set(f'{ang2:.2f}°')
            self._rp_len2_v.set(inches_to_feet(cut2))
            self._rp_diag=dict(length=length,height=height,dim=dim,
                               diag=diag,ang=ang,cut1=cut1,cut2=cut2)
            self._draw_rp_diagram()
        except Exception as e:
            self._rp_diag_v.set(f'Error: {e}')

    def _clear_ramp(self):
        self._rp_len.set(''); self._rp_ht.set(''); self._rp_dim.set('')
        for v in [self._rp_diag_v,self._rp_ang1_v,self._rp_len1_v,
                  self._rp_ang2_v,self._rp_len2_v]: v.set('—')
        self._rp_diag=None
        if hasattr(self,'_rp_cv'): self._rp_cv.delete('all')

    def _sample_ramp(self):
        self._rp_len.set('10'); self._rp_ht.set('1'); self._rp_dim.set('1.5')

    def _on_rp_cfg(self,event):
        self._rp_cv_w=event.width; self._draw_rp_diagram()

    def _draw_rp_diagram(self):
        import math as _m
        c=self._rp_cv; c.delete('all')
        W=getattr(self,'_rp_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_rp_diag',None)
        if not d: self._dph(c,W,H); return
        length=d['length']; height=d['height']; ang=d['ang']
        diag=d['diag']; cut1=d['cut1']; cut2=d['cut2']
        DIM=NAV_BG
        # Reserve space: TOP=40 diagonal label, BOT=46 cut labels, RIGHT=68 height
        PAD_L=16; PAD_R=68; PAD_T=40; PAD_B=46
        avw=W-PAD_L-PAD_R; avh=H-PAD_T-PAD_B
        scale=min(avw/(length or 1), avh/(max(height,0.01)))*0.82
        pw=int(length*scale); ph=int(height*scale)
        thick=max(10, int(d['dim']*scale*0.26))
        # Ramp origin: left end at lower-left, centred vertically
        bx=PAD_L; by=PAD_T+avh//2+ph//2
        tx=bx+pw; ty=by-ph
        sin_a=_m.sin(_m.radians(ang)); cos_a=_m.cos(_m.radians(ang))
        nx=-sin_a; ny=-cos_a   # normal pointing above ramp surface
        p1x=bx;               p1y=by           # bottom-left (lower end, bottom)
        p2x=tx;               p2y=ty           # bottom-right (upper end, bottom)
        p3x=int(tx+thick*nx); p3y=int(ty+thick*ny)  # upper end, top (stringer end)
        p4x=int(bx+thick*nx); p4y=int(by+thick*ny)  # lower end, top (stringer start)
        # ── Ramp body ────────────────────────────────────────────────
        c.create_polygon(p1x,p1y, p2x,p2y, p3x,p3y, p4x,p4y,
                         fill=INPUT_BG, outline='', width=0)
        # ── Stringer: thick ACCENT line along top surface ─────────────
        c.create_line(p4x,p4y, p3x,p3y, fill=ACCENT, width=3)
        # ── Other edges ───────────────────────────────────────────────
        c.create_line(p1x,p1y, p4x,p4y, fill=DIM, width=1)   # left end
        c.create_line(p2x,p2y, p3x,p3y, fill=DIM, width=1)   # right end
        c.create_line(p1x,p1y, p2x,p2y, fill=DIM, width=1)   # bottom edge
        # ── Diagonal label ABOVE stringer, centred (outside ramp) ────
        mx=(p4x+p3x)//2; my=(p4y+p3y)//2
        c.create_text(mx, my-18, text=inches_to_feet(diag),
                      fill=ACCENT, font=('Segoe UI',9,'bold'), anchor='center')
        # ── Ground line (dashed) ──────────────────────────────────────
        c.create_line(bx-4, by, tx+12, by, fill='#AAAAAA', width=1, dash=(3,3))
        # ── Angle arc at lower-left, label BELOW ground line ─────────
        ar=min(pw//6,28)
        c.create_arc(bx-ar,by-ar,bx+ar,by+ar,
                     start=0, extent=ang, style='arc', outline=DIM, width=2)
        c.create_text(bx+4, by+16,
                      text=f'{ang:.1f}°', fill=DIM,
                      font=('Segoe UI',9,'bold'), anchor='w')
        # ── Height arrow RIGHT margin ─────────────────────────────────
        self._va(c, tx+18, ty, by, DIM, inches_to_feet(height), right=True)
        # ── Cut labels at BOTTOM of canvas ───────────────────────────
        c.create_text(PAD_L, H-30,
                      text=f'Cut1 (bottom): {ang:.1f}°   length: {inches_to_ruler(cut1)}',
                      fill=DIM, font=('Segoe UI',8), anchor='w')
        c.create_text(PAD_L, H-14,
                      text=f'Cut2 (top): {90-ang:.1f}°   length: {inches_to_feet(cut2)}',
                      fill=DIM, font=('Segoe UI',8), anchor='w')

    def _build_miter(self):
        tab=self._all_frames["Miter Joint"]
        inner,res=self._two_col(tab)
        self._mj_ang   =self._le(inner,'Corner Angle (°)','90')
        self._mj_thick1=self._le(inner,'Thickness Left (in)','1.5')
        self._mj_thick2=self._le(inner,'Thickness Right (in)','1.5')
        calc_button(tab,'Calculate →',self._calc_miter,
                    clear_cmd=self._clear_miter,sample_cmd=self._sample_miter)
        self._mj_cut1_v=tk.StringVar(value='—')
        self._mj_cut2_v=tk.StringVar(value='—')
        self._rr(res,'Cut Angle 1 (°)',self._mj_cut1_v,color=ACCENT)
        self._rr(res,'Cut Angle 2 (°)',self._mj_cut2_v)

    def _calc_miter(self):
        try:
            import math as _m
            ang=float(self._mj_ang.get())
            t1 =float(self._mj_thick1.get())
            t2 =float(self._mj_thick2.get())
            if t1<=0 or t2<=0: raise ValueError('thickness must be > 0')
            theta=_m.radians(ang)
            a1=_m.degrees(_m.atan2(t2*_m.sin(theta), t1+t2*_m.cos(theta)))
            a2=ang-a1
            self._mj_cut1_v.set(f'{a1:.2f}°')
            self._mj_cut2_v.set(f'{a2:.2f}°')
            self._mj_diag=dict(ang=ang,t1=t1,t2=t2,a1=a1,a2=a2)
            self._draw_mj_diagram()
        except Exception as e:
            self._mj_cut1_v.set(f'Error: {e}')

    def _clear_miter(self):
        self._mj_ang.set(''); self._mj_thick1.set(''); self._mj_thick2.set('')
        self._mj_cut1_v.set('—'); self._mj_cut2_v.set('—')
        self._mj_diag=None
        if hasattr(self,'_mj_cv'): self._mj_cv.delete('all')

    def _sample_miter(self):
        self._mj_ang.set('90'); self._mj_thick1.set('1.5'); self._mj_thick2.set('1.5')

    def _on_mj_cfg(self,event):
        self._mj_cv_w=event.width; self._draw_mj_diagram()

    def _draw_mj_diagram(self):
        import math as _m
        c=self._mj_cv; c.delete('all')
        W=getattr(self,'_mj_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_mj_diag',None)
        if not d: self._dph(c,W,H); return
        ang=d['ang']; t1=d['t1']; t2=d['t2']; a1=d['a1']; a2=d['a2']
        MID=W//2
        GRN='#276749'; RED='#C0392B'

        # ══════════════════════════════════════════════════════════════
        # LEFT PANEL: Corner Assembly View (top-down)
        # ══════════════════════════════════════════════════════════════
        c.create_line(MID,8,MID,H-8,fill=BORDER,width=1,dash=(4,4))
        c.create_text(MID//2,10,text='Corner Assembly View',fill=NAV_BG,
                      font=('Segoe UI',9,'bold'),anchor='n')

        cx=MID//2; cy_top=int(H*0.18); cy_bot=H-30
        piece_len=cy_bot-cy_top
        t_scale=min((MID//2-40)/max(t1,t2,0.1)*0.55, 38)
        t1px=max(10,int(t1*t_scale)); t2px=max(10,int(t2*t_scale))
        half_ca=_m.radians(ang/2)
        l_dir_x=_m.sin(-half_ca);   l_dir_y=_m.cos(half_ca)
        r_dir_x=_m.sin(half_ca);    r_dir_y=_m.cos(half_ca)
        l_px=l_dir_y;  l_py=-l_dir_x
        r_px=-r_dir_y; r_py=r_dir_x

        # Corner piece coords
        L1x=int(cx);                    L1y=int(cy_top)
        L2x=int(cx+l_dir_x*piece_len); L2y=int(cy_top+l_dir_y*piece_len)
        L3x=int(L2x+l_px*t1px);       L3y=int(L2y+l_py*t1px)
        L4x=int(cx+l_px*t1px);        L4y=int(cy_top+l_py*t1px)

        R1x=int(cx);                    R1y=int(cy_top)
        R2x=int(cx+r_dir_x*piece_len); R2y=int(cy_top+r_dir_y*piece_len)
        R3x=int(R2x+r_px*t2px);       R3y=int(R2y+r_py*t2px)
        R4x=int(cx+r_px*t2px);        R4y=int(cy_top+r_py*t2px)

        # Fills — no outline so we can draw edges individually
        c.create_polygon(L1x,L1y,L2x,L2y,L3x,L3y,L4x,L4y,fill=INPUT_BG,outline='')
        c.create_polygon(R1x,R1y,R2x,R2y,R3x,R3y,R4x,R4y,fill=RES_BG,outline='')

        # Left piece edges: solid sides, dashed far end
        c.create_line(L1x,L1y,L2x,L2y, fill=ACCENT,width=2)          # inner (cut face)
        c.create_line(L4x,L4y,L3x,L3y, fill=ACCENT,width=2)          # outer edge
        c.create_line(L1x,L1y,L4x,L4y, fill=ACCENT,width=2)          # top at joint
        c.create_line(L2x,L2y,L3x,L3y, fill=ACCENT,width=2,dash=(6,4))  # far end — dashed

        # Right piece edges: solid sides, dashed far end
        c.create_line(R1x,R1y,R2x,R2y, fill=NAV_BG,width=2)          # inner (cut face)
        c.create_line(R4x,R4y,R3x,R3y, fill=NAV_BG,width=2)          # outer edge
        c.create_line(R1x,R1y,R4x,R4y, fill=NAV_BG,width=2)          # top at joint
        c.create_line(R2x,R2y,R3x,R3y, fill=NAV_BG,width=2,dash=(6,4))  # far end — dashed

        # ── Green joint/seam line (where cut faces meet after assembly) ──
        # Solve for the outer corner: intersection of the two outer edges
        dx_oc=R4x-L4x; dy_oc=R4y-L4y
        det=l_dir_x*(-r_dir_y)-(-r_dir_x)*l_dir_y
        if abs(det)>0.001:
            s_oc=(dx_oc*(-r_dir_y)-(-r_dir_x)*dy_oc)/det
            jx=int(L4x+l_dir_x*s_oc); jy=int(L4y+l_dir_y*s_oc)
            c.create_line(cx,cy_top,jx,jy,fill=GRN,width=2)
            # Small dot at outer corner
            c.create_oval(jx-3,jy-3,jx+3,jy+3,fill=GRN,outline='')

        # ── Corner angle indicator ──
        ar=min(piece_len//5,30)
        l_start_deg=_m.degrees(_m.atan2(-l_dir_y,l_dir_x))
        # Radial arms from joint center to arc endpoints
        arm_l_x=int(cx+l_dir_x*ar); arm_l_y=int(cy_top+l_dir_y*ar)
        arm_r_x=int(cx+r_dir_x*ar); arm_r_y=int(cy_top+r_dir_y*ar)
        c.create_line(cx,cy_top,arm_l_x,arm_l_y,fill='#888',width=1)
        c.create_line(cx,cy_top,arm_r_x,arm_r_y,fill='#888',width=1)
        c.create_arc(cx-ar,cy_top-ar,cx+ar,cy_top+ar,
                     start=l_start_deg,extent=ang,style='arc',outline='#888',width=2)
        c.create_text(cx,cy_top-8,text=f'{ang:.0f}°',fill='#555',
                      font=('Segoe UI',8),anchor='s')

        # Cut angle labels at piece midpoints
        mL_x=int(cx+l_dir_x*piece_len*0.5+l_px*t1px*0.5)
        mL_y=int(cy_top+l_dir_y*piece_len*0.5+l_py*t1px*0.5)
        c.create_text(mL_x-5,mL_y,text=f'{a1:.1f}°',fill=ACCENT,
                      font=('Segoe UI',9,'bold'),anchor='e')
        mR_x=int(cx+r_dir_x*piece_len*0.5+r_px*t2px*0.5)
        mR_y=int(cy_top+r_dir_y*piece_len*0.5+r_py*t2px*0.5)
        c.create_text(mR_x+5,mR_y,text=f'{a2:.1f}°',fill=NAV_BG,
                      font=('Segoe UI',9,'bold'),anchor='w')

        # ══════════════════════════════════════════════════════════════
        # RIGHT PANEL: Miter Cut Angle Detail (board lying flat)
        # ══════════════════════════════════════════════════════════════
        c.create_text(MID+MID//2,10,text='Miter Cut Angle Detail',fill=NAV_BG,
                      font=('Segoe UI',9,'bold'),anchor='n')

        bx=MID+20; by=int(H*0.18); bw2=MID-30; bh2=int(H*0.60)

        # Board fill — no outline; draw edges individually below
        c.create_rectangle(bx,by,bx+bw2,by+bh2,fill='#EEF4FA',outline='')

        # Grain lines (subtle horizontal dashes)
        for gi in range(4):
            gy=by+int(bh2*(gi+1)/5)
            c.create_line(bx+6,gy,bx+bw2-6,gy,fill='#D0E4F0',width=1,dash=(8,5))

        # Miter cut line
        mrad1=_m.radians(abs(a1))
        cut_dx1=int(bh2*_m.tan(mrad1))
        cut_ex1=min(bx+cut_dx1, bx+bw2-8)

        # Waste zone fill
        c.create_polygon(bx,by, cut_ex1,by+bh2, bx,by+bh2,
                         fill='#FFE8CC',outline='',stipple='gray50')
        c.create_polygon(bx,by, cut_ex1,by+bh2, bx,by+bh2,
                         fill='',outline='#E0A060',width=1)

        # Cut line in red
        c.create_line(bx,by, cut_ex1,by+bh2, fill=RED,width=3)

        # Board edges: solid top/left/right, dashed bottom
        c.create_line(bx,by,    bx+bw2,by,     fill=NAV_BG,width=2)          # top
        c.create_line(bx,by,    bx,by+bh2,      fill=NAV_BG,width=2)          # left
        c.create_line(bx+bw2,by,bx+bw2,by+bh2,  fill=NAV_BG,width=2)          # right
        c.create_line(bx,by+bh2,bx+bw2,by+bh2,  fill=NAV_BG,width=2,dash=(6,4))  # bottom — dashed

        # ── Arc at top-left corner (bx,by), spanning from board top-edge to cut line ──
        ar2=26
        # Arc centered at (bx,by): bounding box is (bx-ar2, by-ar2, bx+ar2, by+ar2)
        # start=0° (East = along board top edge), extent=-(90-a1) clockwise to cut line
        c.create_arc(bx-ar2,by-ar2,bx+ar2,by+ar2,
                     start=0,extent=-(90-abs(a1)),style='arc',outline=RED,width=2)
        # Small radial arms for the angle indicator
        c.create_line(bx,by, bx+ar2+4,by,       fill=RED,width=1)  # arm along top edge
        cut_arm_x=int(bx+(ar2+4)*_m.sin(mrad1))  # arm along cut line direction (down-right)
        cut_arm_y=int(by+(ar2+4)*_m.cos(mrad1))
        c.create_line(bx,by, cut_arm_x,cut_arm_y, fill=RED,width=1)
        # Angle label at arc midpoint
        mid_ang_rad=_m.radians(-(90-abs(a1))/2)
        lx=int(bx+(ar2+16)*_m.cos(mid_ang_rad))
        ly=int(by-(ar2+16)*_m.sin(mid_ang_rad))
        c.create_text(lx,ly,text=f'{a1:.1f}°',fill=RED,font=('Segoe UI',9,'bold'),anchor='center')

        # "waste" label — placed in upper region of waste triangle, away from cut line
        waste_lx=bx+max(4, cut_dx1//4)
        waste_ly=by+int(bh2*0.25)
        c.create_text(waste_lx,waste_ly,text='waste',fill='#B07030',
                      font=('Segoe UI',8,'italic'),anchor='nw')

        # Cut angle label above board, Cut 2 below
        c.create_text(bx+bw2//2,by-4,text=f'Cut 1 = {a1:.2f}°',fill=RED,
                      font=('Segoe UI',9,'bold'),anchor='s')
        c.create_text(bx+bw2//2,by+bh2+4,text=f'Cut 2 = {a2:.2f}°',fill=NAV_BG,
                      font=('Segoe UI',9,'bold'),anchor='n')

        # Bottom summary bar
        by2=H-8
        c.create_rectangle(4,by2-18,W-4,by2+2,fill=RES_BG,outline='')
        c.create_text(W//2,by2-8,
                      text=f'Corner: {ang:.0f}°   →   Cut 1 = {a1:.2f}°   |   Cut 2 = {a2:.2f}°',
                      fill=NAV_BG,font=('Segoe UI',9,'bold'),anchor='center')

    def _build_parquet(self):
        tab=self._all_frames["Parquet Floor"]
        inner,res=self._two_col(tab)
        self._pq_rw  =self._le(inner,'Room Width (ft)','12')
        self._pq_rl  =self._le(inner,'Room Length (ft)','10')
        self._pq_bl  =self._le(inner,'Board Length (in)','49')
        self._pq_bw  =self._le(inner,'Board Width (in)','3.5')
        self._pq_wst =self._le(inner,'Waste % (default 10)','10')
        self._pq_dir =self._lo(inner,'Board Direction',
                                ['Boards run along length',
                                 'Boards run across width',
                                 '45° diagonal — Left (\\)',
                                 '45° diagonal — Right (/)'],
                                default='Boards run along length')
        self._pq_stagger=self._lo(inner,'Stagger Pattern',
                                  ['1/4 (25%)','1/3 (33%)','1/2 (50%)',
                                   '2/3 (67%)','3/4 (75%)'],default='1/3 (33%)')
        # Live-update diagram when stagger or direction changes
        self._pq_stagger.trace_add('write', lambda *_: self._calc_parquet())
        self._pq_dir.trace_add('write', lambda *_: self._calc_parquet())
        calc_button(tab,'Calculate →',self._calc_parquet,
                    clear_cmd=self._clear_parquet,sample_cmd=self._sample_parquet)
        self._pq_area_v =tk.StringVar(value='—')
        self._pq_bpr_v  =tk.StringVar(value='—')
        self._pq_rows_v =tk.StringVar(value='—')
        self._pq_tot_v  =tk.StringVar(value='—')
        self._pq_stg_v  =tk.StringVar(value='—')
        self._rr(res,'Total Floor Area (sq ft)',self._pq_area_v,color=ACCENT)
        self._rr(res,'Boards Per Row',          self._pq_bpr_v)
        self._rr(res,'Number of Rows',          self._pq_rows_v)
        self._rr(res,'Total Boards (w/ waste)', self._pq_tot_v)
        self._rr(res,'Stagger Offset (in)',     self._pq_stg_v)

    def _calc_parquet(self):
        try:
            import math as _m
            rw  =float(self._pq_rw.get())*12
            rl  =float(self._pq_rl.get())*12
            bl  =float(self._pq_bl.get())
            bw  =float(self._pq_bw.get())
            wst =float(self._pq_wst.get())/100
            if bl<=0 or bw<=0: raise ValueError('board dims must be > 0')
            # Stagger fraction
            stg_map={'1/4 (25%)':0.25,'1/3 (33%)':1/3,'1/2 (50%)':0.5,
                     '2/3 (67%)':2/3,'3/4 (75%)':0.75}
            stg_frac=stg_map.get(self._pq_stagger.get(),1/3)
            area_sqft=rw*rl/144
            pq_dir=self._pq_dir.get()
            if "45" in pq_dir:
                pq_d="45r" if "Right" in pq_dir else "45l"
                diag_in=_m.sqrt(rl**2+rw**2)
                rows=_m.ceil((rl+rw)/_m.sqrt(2)/bw)
                bpr=_m.ceil(diag_in/bl)
                total=_m.ceil(rows*bpr*(1+wst))
            elif "across" in pq_dir:
                pq_d="across"
                bpr=_m.ceil(rw/bl); rows=_m.ceil(rl/bw)
                total=_m.ceil(bpr*rows*(1+wst))
            else:
                pq_d="along"
                bpr=_m.ceil(rl/bl); rows=_m.ceil(rw/bw)
                total=_m.ceil(bpr*rows*(1+wst))
            stagger_in=round(bl*stg_frac,4)
            self._pq_area_v.set(f'{area_sqft:.2f} sq ft')
            self._pq_bpr_v.set(str(bpr))
            self._pq_rows_v.set(str(rows))
            self._pq_tot_v.set(str(total))
            self._pq_stg_v.set(inches_to_ruler(stagger_in))
            self._pq_diag=dict(rw=rw,rl=rl,bl=bl,bw=bw,bpr=bpr,rows=rows,
                               stg_frac=stg_frac,stg_label=self._pq_stagger.get(),
                               pq_d=pq_d)
            self._draw_pq_diagram()
        except Exception as e:
            self._pq_area_v.set(f'Error: {e}')

    def _clear_parquet(self):
        self._pq_dir.set('Boards run along length')
        self._pq_stagger.set('1/3 (33%)')
        for v in [self._pq_rw,self._pq_rl,self._pq_bl,self._pq_bw,self._pq_wst]:
            v.set('')
        for v in [self._pq_area_v,self._pq_bpr_v,self._pq_rows_v,
                  self._pq_tot_v,self._pq_stg_v]: v.set('—')
        self._pq_diag=None
        if hasattr(self,'_pq_cv'): self._pq_cv.delete('all')

    def _sample_parquet(self):
        self._pq_rw.set('12'); self._pq_rl.set('10')
        self._pq_bl.set('49'); self._pq_bw.set('3.5'); self._pq_wst.set('10')

    def _on_pq_cfg(self,event):
        self._pq_cv_w=event.width; self._draw_pq_diagram()

    def _draw_pq_diagram(self):
        import math as _m
        c=self._pq_cv; c.delete('all')
        W=getattr(self,'_pq_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_pq_diag',None)
        if not d: self._dph(c,W,H); return
        rw=d['rw']; rl=d['rl']; bl=d['bl']; bw=d['bw']
        stg_frac=d.get('stg_frac',1/3)
        stg_label=d.get('stg_label','1/3 (33%)')
        pq_d=d.get('pq_d','along')
        GRN='#276749'; DIM=NAV_BG
        # Layout zones — labels OUTSIDE the floor area
        PAD_L=95; PAD_R=90; TOP=22; BOT=78
        DW=W-PAD_L-PAD_R; DH=H-TOP-BOT
        if DW<10 or DH<10: return
        # ── 45° diagonal ──
        if pq_d in ("45l","45r"):
            import math as _pm
            slash=(pq_d=="45r")
            sc_x2=DW/(rl or 1); sc_y2=DH/(rw or 1); sc_a=(sc_x2+sc_y2)/2
            step_c=bw*sc_a*_pm.sqrt(2); bw_c=bw*sc_a*_pm.sqrt(2)*0.88
            x0=PAD_L; y0=TOP; x1=PAD_L+DW; y1=TOP+DH
            c.create_rectangle(x0,y0,x1,y1,fill='#F8FAFC',outline='#999',width=1)
            def _pix(ax,ay,bx,by,cv,sl):
                pts=[]
                def chk(x,y):
                    if ax<=x<=bx and ay<=y<=by: pts.append((x,y))
                if sl: chk(cv-ay,ay);chk(cv-by,by);chk(ax,cv-ax);chk(bx,cv-bx)
                else:  chk(ay-cv,ay);chk(by-cv,by);chk(ax,ax+cv);chk(bx,bx+cv)
                seen=set();u=[]
                for p in pts:
                    k=(round(p[0]),round(p[1]))
                    if k not in seen: seen.add(k);u.append(p)
                return u[:2]
            c_st=(x0+y0) if slash else (y0-x1)
            c_en=(x1+y1) if slash else (y1-x0)
            n_s=int((c_en-c_st)/step_c)+3 if step_c>0 else 1
            blen_pq=bl*sc_a  # board length in px (bl in inches, sc_a in px/in)
            for k in range(-1,n_s+1):
                c1v=c_st+k*step_c; c2v=c1v+bw_c
                p1=_pix(x0,y0,x1,y1,c1v,slash); p2=_pix(x0,y0,x1,y1,c2v,slash)
                if len(p1)==2 and len(p2)==2:
                    flat=[v for pt in p1+list(reversed(p2)) for v in pt]
                    c.create_polygon(flat,fill=INPUT_BG if k%2==0 else RES_BG,outline="")
                if len(p1)==2:
                    c.create_line(p1[0][0],p1[0][1],p1[1][0],p1[1][1],fill=GRN,width=2)
            # Per-stripe staggered board-end cuts (Liang-Barsky clipped)
            def _lcp(ax,ay,bx,by):
                dx=bx-ax; dy=by-ay; t0=0.0; t1=1.0
                for p,q in [(-dx,ax-x0),(dx,x1-ax),(-dy,ay-y0),(dy,y1-ay)]:
                    if p==0:
                        if q<0: return None
                    elif p<0:
                        r=q/p
                        if r>t1: return None
                        if r>t0: t0=r
                    else:
                        r=q/p
                        if r<t0: return None
                        if r<t1: t1=r
                return ax+t0*dx,ay+t0*dy,ax+t1*dx,ay+t1*dy
            if blen_pq>4:
                if slash: cst2=y0-x1; cen2=y1-x0
                else:     cst2=x0+y0; cen2=x1+y1
                for k2 in range(-1,n_s+1):
                    c1k=c_st+k2*step_c; c2k=c1k+bw_c
                    nc2=int((cen2-cst2)/blen_pq)+3
                    cut_off=(blen_pq*stg_frac) if k2%2==1 else 0
                    for j in range(-1,nc2+1):
                        cv3=cst2+cut_off+j*blen_pq
                        if not slash:
                            xp1=(cv3-c1k)/2; yp1=(cv3+c1k)/2
                            xp2=(cv3-c2k)/2; yp2=(cv3+c2k)/2
                        else:
                            xp1=(c1k-cv3)/2; yp1=(c1k+cv3)/2
                            xp2=(c2k-cv3)/2; yp2=(c2k+cv3)/2
                        seg=_lcp(xp1,yp1,xp2,yp2)
                        if seg: c.create_line(seg[0],seg[1],seg[2],seg[3],fill=GRN,width=2)
            c.create_rectangle(x0,y0,x1,y1,fill='',outline=ACCENT,width=1)
            dir_lbl="45° Right (/)" if slash else "45° Left (\\)"
            c.create_text(x0,y0-4,text=f'Boards {bl}" × {bw}"  ({dir_lbl})',
                          fill='#555',font=('Segoe UI',9,'bold'),anchor='sw')
            self._ha(c,x0,y1+54,x1,DIM,f'Length: {rl/12:.1f} ft',above=False)
            self._va(c,x0-10,y0,y1,DIM,f'Width {rw/12:.1f} ft',right=False)
            return
        # ── across width (swap run/stack dims) ──
        if pq_d=="across":
            sc_x=DW/(rw or 1)
            bl_px=bl*sc_x
            bw_px_ideal=bw*DH/(rl or 1)
            bw_px=max(14,bw_px_ideal)
            x0=PAD_L; y0=TOP; x1=PAD_L+DW; y1_max=TOP+DH
            stagger_px=bl_px*stg_frac
            c.create_rectangle(x0,y0,x1,y1_max,fill='#F8FAFC',outline='#999',width=1)
            row=0; y=y0
            while y<y1_max and row<60:
                bh=max(14,min(bw_px,y1_max-y))
                offset=(bl_px*stg_frac*row)%bl_px; bx=x0-offset
                while bx<x1:
                    dx0=max(x0,bx); dx1=min(x1,bx+bl_px)
                    if dx0<dx1: c.create_rectangle(dx0,y,dx1,y+bh,fill=INPUT_BG,outline=ACCENT,width=1)
                    if x0+1<bx<x1-1: c.create_line(bx,y,bx,y+bh,fill=GRN,width=2)
                    bx+=bl_px
                y+=bw_px; row+=1
            lx=x1+10
            if bw_px>4:
                c.create_line(lx,y0,lx,y0+bw_px,fill=DIM,width=1,arrow='both')
                c.create_text(lx+4,y0+bw_px/2,text=f'{bw}"',fill=DIM,font=('Segoe UI',8),anchor='w')
            ann1=y1_max+14
            if bl_px<DW:
                c.create_line(x0+2,ann1,x0+bl_px-2,ann1,fill=GRN,width=2,arrow='both')
                c.create_text(x0+bl_px/2,ann1-10,text=f'Board: {bl}"',
                              fill=GRN,font=('Segoe UI',9,'bold'),anchor='center')
            ann2=y1_max+36
            if stagger_px>4:
                c.create_line(x0+2,ann2,x0+stagger_px-2,ann2,fill=GRN,width=1,
                              arrow='both',dash=(4,3))
                c.create_text(x0+stagger_px/2,ann2-10,text=f'Stagger {stg_label}',
                              fill=GRN,font=('Segoe UI',8),anchor='center')
            c.create_text(x0,y0-4,text=f'Boards {bl}" × {bw}"  (across width)',
                          fill='#555',font=('Segoe UI',9,'bold'),anchor='sw')
            c.create_line(x1-40,y0-4,x1-28,y0-4,fill=GRN,width=2)
            c.create_text(x1-26,y0-4,text='= joint',fill=GRN,font=('Segoe UI',8),anchor='w')
            self._ha(c,x0,y1_max+54,x1,DIM,f'Width: {rw/12:.1f} ft',above=False)
            self._va(c,x0-10,y0,y1_max,DIM,f'Length {rl/12:.1f} ft',right=False)
            return
        sc_x=DW/(rl or 1)
        # Ensure each board row is at least 14px so stagger is visible
        bl_px=bl*sc_x
        bw_px_ideal=bw*DH/(rw or 1)
        bw_px=max(14, bw_px_ideal)
        x0=PAD_L; y0=TOP; x1=PAD_L+DW; y1_max=TOP+DH
        stagger_px=bl_px*stg_frac
        # Floor background (show only up to DH)
        c.create_rectangle(x0,y0,x1,y1_max,fill='#F8FAFC',outline='#999',width=1)
        # Draw board rows
        row=0; y=y0
        while y<y1_max and row<60:
            bh=max(14,min(bw_px, y1_max-y))
            # Cumulative stagger offset, wraps within one board length
            offset=(bl_px*stg_frac*row)%bl_px
            bx=x0-offset
            while bx<x1:
                dx0=max(x0,bx); dx1=min(x1,bx+bl_px)
                if dx0<dx1:
                    c.create_rectangle(dx0,y,dx1,y+bh,fill=INPUT_BG,outline=ACCENT,width=1)
                # Green joint line at board start (inside floor only)
                if x0+1<bx<x1-1:
                    c.create_line(bx,y,bx,y+bh,fill=GRN,width=2)
                bx+=bl_px
            y+=bw_px; row+=1
        # ── Labels OUTSIDE floor area ─────────────────────────────────
        # Board width annotation (right margin, first row)
        lx=x1+10
        if bw_px>4:
            c.create_line(lx,y0,lx,y0+bw_px,fill=DIM,width=1,arrow='both')
            c.create_text(lx+4,y0+bw_px/2,text=f'{bw}"',
                          fill=DIM,font=('Segoe UI',8),anchor='w')
        # Board length arrow BELOW floor (row 1 in the annotation zone)
        ann1=y1_max+14
        if bl_px<DW:
            c.create_line(x0+2,ann1,x0+bl_px-2,ann1,fill=GRN,width=2,arrow='both')
            c.create_text(x0+bl_px/2,ann1-10,
                          text=f'Board length: {bl}"',
                          fill=GRN,font=('Segoe UI',9,'bold'),anchor='center')
        # Stagger offset arrow (dashed) below board length
        ann2=y1_max+36
        if stagger_px>4:
            c.create_line(x0+2,ann2,x0+stagger_px-2,ann2,fill=GRN,width=1,
                          arrow='both',dash=(4,3))
            c.create_text(x0+stagger_px/2,ann2-10,
                          text=f'Stagger {stg_label}',
                          fill=GRN,font=('Segoe UI',8),anchor='center')
        # Room dimension arrows
        self._ha(c,x0,y1_max+54,x1,DIM,f'Length: {rl/12:.1f} ft',above=False)
        self._va(c,x0-10,y0,y1_max,DIM,f'Width {rw/12:.1f} ft',right=False)
        # Description top-left
        c.create_text(x0,y0-4,
                      text=f'Boards {bl}" × {bw}"',
                      fill='#555',font=('Segoe UI',9,'bold'),anchor='sw')
        # Joint legend top-right
        c.create_line(x1-40,y0-4,x1-28,y0-4,fill=GRN,width=2)
        c.create_text(x1-26,y0-4,text='= joint',fill=GRN,font=('Segoe UI',8),anchor='w')

    def _build_crown(self):
        import math as _m
        tab=self._all_frames["Crown Molding"]
        inner,res=self._two_col(tab)
        self._cm_spring =self._lo(inner,'Spring Angle',
                                   ['38°','45°','52°','Custom'],default='45°')
        self._cm_custom =self._le(inner,'Custom Spring Angle (°)','45')
        self._cm_corner =self._le(inner,'Corner Angle (°)','90')
        self._cm_type   =self._lo(inner,'Corner Type',
                                   ['Inside','Outside'],default='Inside')
        calc_button(tab,'Calculate →',self._calc_crown,
                    clear_cmd=self._clear_crown,sample_cmd=self._sample_crown)
        self._cm_miter_v =tk.StringVar(value='—')
        self._cm_bevel_v =tk.StringVar(value='—')
        self._cm_ref_v   =tk.StringVar(value='—')
        self._rr(res,'Miter Angle (°)',       self._cm_miter_v,color=ACCENT)
        self._rr(res,'Bevel Angle (°)',        self._cm_bevel_v)
        self._rr(res,'Common 45° Spring ref', self._cm_ref_v)

    def _calc_crown(self):
        try:
            import math as _m
            sp_str=self._cm_spring.get()
            if sp_str=='Custom':
                sp=float(self._cm_custom.get())
            else:
                sp=float(sp_str.replace('°',''))
            corner=float(self._cm_corner.get())
            half=_m.radians(corner/2)
            s=_m.radians(sp)
            miter=_m.degrees(_m.atan(_m.cos(s)*_m.tan(half)))
            bevel=_m.degrees(_m.asin(_m.sin(s)*_m.sin(half)))
            self._cm_miter_v.set(f'{miter:.2f}°')
            self._cm_bevel_v.set(f'{bevel:.2f}°')
            # Reference row for 45° spring, same corner
            m45=_m.degrees(_m.atan(_m.cos(_m.radians(45))*_m.tan(half)))
            b45=_m.degrees(_m.asin(_m.sin(_m.radians(45))*_m.sin(half)))
            self._cm_ref_v.set(f'Miter {m45:.1f}°  Bevel {b45:.1f}°')
            self._cm_diag=dict(sp=sp,corner=corner,miter=miter,bevel=bevel)
            self._draw_cm_diagram()
        except Exception as e:
            self._cm_miter_v.set(f'Error: {e}')

    def _clear_crown(self):
        self._cm_custom.set(''); self._cm_corner.set('')
        for v in [self._cm_miter_v,self._cm_bevel_v,self._cm_ref_v]: v.set('—')
        self._cm_diag=None
        if hasattr(self,'_cm_cv'): self._cm_cv.delete('all')

    def _sample_crown(self):
        self._cm_spring.set('45°'); self._cm_corner.set('90')

    def _on_cm_cfg(self,event):
        self._cm_cv_w=event.width; self._draw_cm_diagram()


    def _build_cm_chart(self):
        """Reference chart: miter+bevel for common spring angles and corners."""
        import math as _m
        frame = self._all_frames["Crown Molding"]

        def calc_crown(corner_deg, spring_deg):
            c2 = _m.radians(corner_deg / 2)
            s  = _m.radians(spring_deg)
            miter = _m.degrees(_m.atan(_m.cos(s) / _m.tan(c2)))
            bevel = _m.degrees(_m.asin(_m.sin(s) * _m.sin(c2)))
            return miter, bevel

        card = make_card(frame)
        card.pack(fill="x", padx=10, pady=(0, 10))
        section_header(card, "  MITER & BEVEL REFERENCE CHART")

        tk.Label(card, text="Molding flat on table — angles for left/right inside corners:",
                 font=("Segoe UI", 9), fg=MUTED, bg=CARD, anchor="w"
                 ).pack(anchor="w", padx=12, pady=(2, 4))

        # Header row
        hdr = ctk.CTkFrame(card, fg_color=NAV_BG, corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=(0, 1))
        for txt, w in [("Corner Angle", 100), ("Spring 38°", 130),
                       ("Spring 45°", 130), ("Spring 52°", 130)]:
            ctk.CTkLabel(hdr, text=txt, width=w,
                         font=ctk.CTkFont("Segoe UI", 10, "bold"),
                         text_color="white", anchor="center"
                         ).pack(side="left", padx=6, pady=5)

        corners = [("45°",45),("60°",60),("72°",72),("90°",90),("120°",120),("135°",135)]
        springs = [38, 45, 52]
        row_colors = [CARD, INPUT_BG]
        for ri, (lbl, deg) in enumerate(corners):
            row = ctk.CTkFrame(card, fg_color=row_colors[ri%2], corner_radius=0)
            row.pack(fill="x", padx=8, pady=1)
            ctk.CTkLabel(row, text=lbl, width=100,
                         font=ctk.CTkFont("Segoe UI", 10, "bold"),
                         text_color=TEXT, anchor="center"
                         ).pack(side="left", padx=6, pady=3)
            for sp in springs:
                try:
                    m, b = calc_crown(deg, sp)
                    val = f"M: {m:.1f}°   B: {b:.1f}°"
                except Exception:
                    val = "—"
                ctk.CTkLabel(row, text=val, width=130,
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=TEXT, anchor="center"
                             ).pack(side="left", padx=6, pady=3)

        # Cutting instructions box
        note = ctk.CTkFrame(card, fg_color=RES_BG, corner_radius=6)
        note.pack(fill="x", padx=8, pady=(6, 10))
        ctk.CTkLabel(note, text="📐  How to use these angles on a compound miter saw:",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=TEXT, anchor="w").pack(anchor="w", padx=10, pady=(6, 2))
        steps = (
            "1. Lay molding FLAT on the saw table — do not stand it at the spring angle\n"
            "2. MITER: rotate the saw table (left for left corner, right for right corner)\n"
            "3. BEVEL: tilt the saw blade away from the fence\n"
            "4. For outside corners, use the same angles but reverse the miter direction"
        )
        tk.Label(note, text=steps, font=("Segoe UI", 9), fg=TEXT, bg=RES_BG,
                 justify="left", anchor="w").pack(anchor="w", padx=10, pady=(0, 8))

    def _draw_cm_diagram(self):
        import math as _m
        c=self._cm_cv; c.delete('all')
        W=getattr(self,'_cm_cv_w',0) or c.winfo_width() or 500
        H=int(c.cget('height'))
        d=getattr(self,'_cm_diag',None)
        if not d: self._dph(c,W,H); return
        sp=d['sp']; miter=d['miter']; bevel=d['bevel']
        GRN='#276749'; RED='#C0392B'

        # ══ LEFT: Cross-section — wall + ceiling corner with molding ══════
        cx=int(W*0.27); cy=int(H*0.72); arm=int(min(W*0.22,H*0.46))
        # Wall fill block
        c.create_rectangle(cx-14,cy-arm,cx,cy+arm//5,fill='#D8E8F4',outline='')
        c.create_line(cx,cy-arm,cx,cy+arm//5,fill=NAV_BG,width=4)
        # (WALL label drawn last so it is never hidden behind polygons)
        # Ceiling fill block
        c.create_rectangle(cx-arm//8,cy-arm-14,cx+arm,cy-arm,fill='#D8E8F4',outline='')
        c.create_line(cx-arm//8,cy-arm,cx+arm,cy-arm,fill=NAV_BG,width=4)
        # (CEILING label drawn last — polygon extends above ceiling line and would cover it)
        c.create_oval(cx-4,cy-arm-4,cx+4,cy-arm+4,fill=NAV_BG,outline='')
        # Molding body at spring angle
        dx=_m.cos(_m.radians(90-sp)); dy=-_m.sin(_m.radians(90-sp))
        thick=22; mlen=int(arm*0.78)
        px=-dy; py=dx
        pts=[
            int(cx+thick*px),         int(cy-arm+thick*py),
            int(cx+mlen*dx+thick*px), int(cy-arm+mlen*dy+thick*py),
            int(cx+mlen*dx),          int(cy-arm+mlen*dy),
            cx, cy-arm
        ]
        # Drop shadow
        spts=[p+4 if j%2==0 else p+4 for j,p in enumerate(pts)]
        c.create_polygon(spts,fill='#B0C8DC',outline='')
        c.create_polygon(pts,fill='#EEF4FA',outline=NAV_BG,width=2)
        # Grain lines
        for frac in [0.3,0.55,0.75]:
            gx0=int(cx+frac*mlen*dx); gy0=int(cy-arm+frac*mlen*dy)
            c.create_line(gx0,gy0,int(gx0+thick*px*0.7),int(gy0+thick*py*0.7),
                          fill='#A8C8E0',width=1)
        # Spring angle arc
        ar=26
        c.create_arc(cx-ar,cy-arm-ar,cx+ar,cy-arm+ar,
                     start=0,extent=90-sp,style='arc',outline=GRN,width=2)
        c.create_text(cx+ar+20,cy-arm+5,text=f'{sp:.0f}° spring',fill=GRN,
                      font=('Segoe UI',9,'bold'),anchor='w')
        c.create_text(cx+4,cy+arm//5+10,text='Cross-section view',
                      fill=MUTED,font=('Segoe UI',8,'italic'),anchor='w')
        # WALL and CEILING drawn last — always on top of all polygons
        c.create_text(cx-18,cy-arm//2,text='WALL',fill=NAV_BG,
                      font=('Segoe UI',8,'bold'),anchor='e')
        c.create_text(cx+arm//2,cy-arm-20,text='CEILING',fill=NAV_BG,
                      font=('Segoe UI',8,'bold'),anchor='s')

        # ══ RIGHT: Board lying flat — shows miter cut + bevel tilt ═══════
        rx=int(W*0.60); ry=int(H*0.10); bw=int(W*0.31); bh=int(H*0.44)
        c.create_text(rx+bw//2,ry-3,text='Piece flat on saw table',
                      fill=NAV_BG,font=('Segoe UI',9,'bold'),anchor='s')
        # Board face
        c.create_rectangle(rx,ry,rx+bw,ry+bh,fill='#EEF4FA',outline=NAV_BG,width=2)
        # Length-direction wood grain
        for gi in range(3):
            gy=ry+int(bh*(gi+1)/4)
            c.create_line(rx+6,gy,rx+bw-6,gy,fill='#D0E4F0',width=1,dash=(8,6))

        # ─ MITER cut (red angled line, left side of board) ─
        mrad=_m.radians(abs(miter))
        cut_dx=int(bh*_m.tan(mrad))
        cut_ex=min(rx+cut_dx, rx+bw-8)
        # Waste zone (what gets cut off)
        c.create_polygon(rx,ry, cut_ex,ry+bh, rx,ry+bh,
                         fill='#FFE8CC',outline='',stipple='gray50')
        c.create_polygon(rx,ry, cut_ex,ry+bh, rx,ry+bh, fill='',outline='#E0A060',width=1)
        c.create_line(rx,ry, cut_ex,ry+bh, fill=RED,width=3)
        # Miter angle arc at top-left
        ar2=22
        c.create_arc(rx,ry,rx+ar2*2,ry+ar2*2,
                     start=270,extent=-(90-abs(miter)),style='arc',outline=RED,width=2)
        c.create_text(rx-6,ry+bh//2,
                      text=f'MITER\n{miter:.1f}°\n(table\nrotation)',
                      fill=RED,font=('Segoe UI',8,'bold'),anchor='e')

        # ─ BEVEL tilt (green dashed diagonal across board face) ─
        bmx=rx+bw//2; bmy=ry+bh//2
        bspan=int(min(bw,bh)*0.30)
        boff=int(bspan*_m.tan(_m.radians(max(0.5,abs(bevel)))))
        c.create_line(bmx-boff,bmy-bspan, bmx+boff,bmy+bspan,
                      fill=GRN,width=2,dash=(7,4))
        # Bevel arc indicator
        c.create_arc(bmx-18,bmy-18,bmx+18,bmy+18,
                     start=90,extent=int(bevel),style='arc',outline=GRN,width=2)
        c.create_text(rx+bw+8,bmy,
                      text=f'BEVEL\n{bevel:.1f}°\n(blade\ntilt)',
                      fill=GRN,font=('Segoe UI',8,'bold'),anchor='w')

        # Board edge labels
        c.create_text(rx+bw//2,ry+bh+5,text='⬆ fence side',
                      fill=MUTED,font=('Segoe UI',7,'italic'),anchor='n')

        # ══ BOTTOM SUMMARY BAR ════════════════════════════════════════════
        by=H-6
        c.create_rectangle(8,by-20,W-8,by+2,fill=RES_BG,outline='')
        c.create_text(W//2,by-8,
                      text=f'Set saw:  MITER = {miter:.1f}°  (rotate table)     BEVEL = {bevel:.1f}°  (tilt blade)     Spring = {sp:.0f}°',
                      fill=NAV_BG,font=('Segoe UI',10,'bold'),anchor='center')



# ─────────────────────────────────────────────────────────────────────────────
# FINANCE: Compound Interest + ROI (injected before FinanceCalcTab)
# ─────────────────────────────────────────────────────────────────────────────
class CompoundInterestCalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _calculate(self):
        try:
            import math as _m
            P   = float(self._ci_prin.get())
            r   = float(self._ci_rate.get()) / 100
            n   = {"Annual (1)":1,"Semi-Annual (2)":2,"Quarterly (4)":4,
                   "Monthly (12)":12,"Daily (365)":365}.get(self._ci_freq.get(),12)
            t   = float(self._ci_yrs.get())
            FV  = P * (1 + r/n) ** (n*t)
            APY = (1 + r/n)**n - 1
            dbl = 72 / (r*100) if r > 0 else float('inf')
            self._ci_fv_v.set(f'${FV:,.2f}')
            self._ci_int_v.set(f'${FV-P:,.2f}')
            self._ci_apy_v.set(f'{APY*100:.4f}%')
            self._ci_dbl_v.set(f'{dbl:.1f} yrs (Rule of 72)')
        except Exception as e:
            self._ci_fv_v.set(f'Error: {e}')

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._ci_prin = labeled_entry(inner,'Principal ($)','10000', on_enter=self._calculate)
        self._ci_rate = labeled_entry(inner,'Annual Rate (%)','5.0', on_enter=self._calculate)
        self._ci_freq = labeled_option(inner,'Compounding',
            ['Annual (1)','Semi-Annual (2)','Quarterly (4)','Monthly (12)','Daily (365)'],
            default='Monthly (12)')
        self._ci_yrs  = labeled_entry(inner,'Time (years)','10', on_enter=self._calculate)
        calc_button(self,'Calculate →',self._calculate,
                    clear_cmd=self._clear,sample_cmd=self._sample)
        res = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._ci_fv_v  = tk.StringVar(value='—')
        self._ci_int_v = tk.StringVar(value='—')
        self._ci_apy_v = tk.StringVar(value='—')
        self._ci_dbl_v = tk.StringVar(value='—')
        result_row(res,'Future Value',        self._ci_fv_v, color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Interest Earned',     self._ci_int_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Effective APY',       self._ci_apy_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Years to Double',     self._ci_dbl_v,lbl_fs=10,val_fs=11,row_h=34)

        # Rule of 72 info box
        info = ctk.CTkFrame(self, fg_color=RES_BG, corner_radius=8)
        info.pack(fill='x', padx=20, pady=(4,8))
        ctk.CTkLabel(info, text='📌  Rule of 72 — What Is It?',
                     font=ctk.CTkFont('Segoe UI',15,'bold'),
                     text_color=TEXT).pack(anchor='w', padx=14, pady=(10,4))
        ctk.CTkLabel(info,
                     text=('Divide 72 by the annual interest rate to estimate how many years money takes to double.\n\n'
                           'Example:  6% rate  →  72 ÷ 6 = 12 years to double\n'
                           'Example:  9% rate  →  72 ÷ 9 = 8 years to double\n\n'
                           'Works best between 4%–12%.  For continuous compounding use 69.3 instead.\n'
                           'Reverse: divide 72 by the years to find the required rate.'),
                     font=ctk.CTkFont('Segoe UI',13),
                     text_color=TEXT, justify='left', anchor='w', wraplength=620
                     ).pack(anchor='w', padx=14, pady=(0,12))

    def _clear(self):
        for v in [self._ci_prin,self._ci_rate,self._ci_yrs]: v.set('')
        for v in [self._ci_fv_v,self._ci_int_v,self._ci_apy_v,self._ci_dbl_v]: v.set('—')

    def _sample(self):
        self._ci_prin.set('10000'); self._ci_rate.set('5.0')
        self._ci_freq.set('Monthly (12)'); self._ci_yrs.set('10')


class ROICalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _calculate(self):
        try:
            import math as _m
            cost = float(self._roi_cost.get())
            fv   = float(self._roi_fv.get())
            yrs  = float(self._roi_yrs.get()) if self._roi_yrs.get().strip() else 1
            gain = fv - cost
            roi  = gain / cost * 100 if cost else 0
            ann  = ((fv/cost)**(1/yrs) - 1)*100 if cost and yrs else 0
            self._roi_gain_v.set(f'${gain:,.2f}')
            self._roi_pct_v.set(f'{roi:.2f}%')
            self._roi_ann_v.set(f'{ann:.2f}% / year')
            self._roi_r72_v.set(f'{72/ann:.1f} yrs' if ann>0 else 'N/A')
        except Exception as e:
            self._roi_gain_v.set(f'Error: {e}')

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._roi_cost = labeled_entry(inner,'Initial Investment ($)','10000', on_enter=self._calculate)
        self._roi_fv   = labeled_entry(inner,'Final Value ($)','15000', on_enter=self._calculate)
        self._roi_yrs  = labeled_entry(inner,'Time Period (years)','5', on_enter=self._calculate)
        calc_button(self,'Calculate →',self._calculate,
                    clear_cmd=self._clear,sample_cmd=self._sample)
        res = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._roi_gain_v = tk.StringVar(value='—')
        self._roi_pct_v  = tk.StringVar(value='—')
        self._roi_ann_v  = tk.StringVar(value='—')
        self._roi_r72_v  = tk.StringVar(value='—')
        result_row(res,'Total Gain / Loss',   self._roi_gain_v,color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total ROI (%)',        self._roi_pct_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Annualized ROI',       self._roi_ann_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Years to Double',      self._roi_r72_v, lbl_fs=10,val_fs=11,row_h=34)

    def _clear(self):
        for v in [self._roi_cost,self._roi_fv,self._roi_yrs]: v.set('')
        for v in [self._roi_gain_v,self._roi_pct_v,self._roi_ann_v,self._roi_r72_v]: v.set('—')

    def _sample(self):
        self._roi_cost.set('10000'); self._roi_fv.set('15000'); self._roi_yrs.set('5')


# ─────────────────────────────────────────────────────────────────────────────
# IT NETWORKING TAB
# ─────────────────────────────────────────────────────────────────────────────
class ITNetworkingCalcTab(CalcTabMixin, ctk.CTkFrame):

    ALL_CALCS = ["Binary-Hex", "IP Converter", "IPv6 Calculator",
                 "Subnet / CIDR", "Subnet Cheat Sheet", "Supernet"]

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}
        self._active_calc = self.ALL_CALCS[0]
        self._build()

    def _calculate(self):
        fn = {"Subnet / CIDR":   self._calc_subnet,
              "Supernet":        self._calc_supernet,
              "IP Converter":    self._calc_ipconv,
              "Binary-Hex":      self._calc_binhex,
              "IPv6 Calculator": self._calc_ipv6}.get(self._active_calc)
        if fn: fn()

    def show_calculator(self, name):
        for f in self._all_frames.values(): f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    def _build(self):
        for name in self.ALL_CALCS:
            if name in ("Subnet Cheat Sheet","Binary-Hex","IPv6 Calculator"):
                self._all_frames[name] = ctk.CTkFrame(self, fg_color=APP_BG)
            else:
                self._all_frames[name] = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._build_subnet(); self._build_supernet(); self._build_ipconv()
        self._build_binhex(); self._build_cheatsheet(); self._build_ipv6()
        self.show_calculator(self.ALL_CALCS[0])

    # ── SUBNET / CIDR ────────────────────────────────────────────────────
    def _build_subnet(self):
        tab = self._all_frames["Subnet / CIDR"]
        ctk.CTkLabel(tab, text="Subnet / CIDR Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(inner, text="Enter IP/CIDR  e.g. 192.168.1.0/24  or  192.168.1.0  +  prefix",
                     font=ctk.CTkFont("Segoe UI",9), text_color=MUTED, anchor='w').pack(anchor='w',padx=16,pady=(8,2))
        self._sn_cidr   = labeled_entry(inner, 'IP Address / CIDR', '192.168.1.0/24', on_enter=self._calculate)
        self._sn_prefix = labeled_entry(inner, 'Prefix (if no /)',   '24', on_enter=self._calculate)
        calc_button(tab, 'Calculate →', self._calc_subnet,
                    clear_cmd=self._clear_subnet, sample_cmd=self._sample_subnet)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._sn_net_v   = tk.StringVar(value='—'); self._sn_bcast_v = tk.StringVar(value='—')
        self._sn_first_v = tk.StringVar(value='—'); self._sn_last_v  = tk.StringVar(value='—')
        self._sn_mask_v  = tk.StringVar(value='—'); self._sn_wild_v  = tk.StringVar(value='—')
        self._sn_cidr_v  = tk.StringVar(value='—'); self._sn_hosts_v = tk.StringVar(value='—')
        self._sn_class_v = tk.StringVar(value='—')
        result_row(res,'Network Address',   self._sn_net_v,  color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Broadcast Address', self._sn_bcast_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'First Host',        self._sn_first_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Last Host',         self._sn_last_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Subnet Mask',       self._sn_mask_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Wildcard Mask',     self._sn_wild_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'CIDR Notation',     self._sn_cidr_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Usable Hosts',      self._sn_hosts_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'IP Class / Type',   self._sn_class_v,lbl_fs=10,val_fs=11,row_h=34)

    def _calc_subnet(self):
        try:
            import ipaddress as _ip
            inp = self._sn_cidr.get().strip()
            if '/' not in inp:
                inp = inp + '/' + self._sn_prefix.get().strip()
            net = _ip.IPv4Network(inp, strict=False)
            hosts = list(net.hosts())
            usable = max(0, net.num_addresses - 2) if net.prefixlen < 31 else net.num_addresses
            fo = int(str(net.network_address).split('.')[0])
            cls = ('A' if fo<128 else 'B' if fo<192 else 'C' if fo<224 else 'D' if fo<240 else 'E')
            pub = ('Private' if net.network_address.is_private else
                   'Loopback' if net.network_address.is_loopback else 'Public')
            self._sn_net_v.set(str(net.network_address))
            self._sn_bcast_v.set(str(net.broadcast_address))
            self._sn_first_v.set(str(hosts[0]) if hosts else 'N/A')
            self._sn_last_v.set(str(hosts[-1]) if hosts else 'N/A')
            self._sn_mask_v.set(str(net.netmask))
            self._sn_wild_v.set(str(net.hostmask))
            self._sn_cidr_v.set(f'{net.network_address}/{net.prefixlen}')
            self._sn_hosts_v.set(f'{usable:,}')
            self._sn_class_v.set(f'Class {cls}  —  {pub}')
        except Exception as e:
            self._sn_net_v.set(f'Error: {e}')

    def _clear_subnet(self):
        self._sn_cidr.set(''); self._sn_prefix.set('')
        for v in [self._sn_net_v,self._sn_bcast_v,self._sn_first_v,self._sn_last_v,
                  self._sn_mask_v,self._sn_wild_v,self._sn_cidr_v,self._sn_hosts_v,
                  self._sn_class_v]: v.set('—')

    def _sample_subnet(self):
        self._sn_cidr.set('192.168.1.0/24'); self._sn_prefix.set('24')

    # ── SUPERNET ──────────────────────────────────────────────────────────
    def _build_supernet(self):
        tab = self._all_frames["Supernet"]
        ctk.CTkLabel(tab, text="Supernet Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(inner, text="Enter subnets in CIDR notation to find their supernet",
                     font=ctk.CTkFont("Segoe UI",9), text_color=MUTED, anchor='w').pack(anchor='w',padx=16,pady=(8,2))
        self._sp_n1 = labeled_entry(inner,'Subnet 1','192.168.0.0/24', on_enter=self._calculate)
        self._sp_n2 = labeled_entry(inner,'Subnet 2','192.168.1.0/24', on_enter=self._calculate)
        self._sp_n3 = labeled_entry(inner,'Subnet 3 (optional)','', on_enter=self._calculate)
        self._sp_n4 = labeled_entry(inner,'Subnet 4 (optional)','', on_enter=self._calculate)
        calc_button(tab,'Calculate Supernet',self._calc_supernet,
                    clear_cmd=self._clear_supernet,sample_cmd=self._sample_supernet)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._sp_snet_v  = tk.StringVar(value='—'); self._sp_pfx_v   = tk.StringVar(value='—')
        self._sp_hosts_v = tk.StringVar(value='—'); self._sp_nets_v  = tk.StringVar(value='—')
        self._sp_mask_v  = tk.StringVar(value='—')
        result_row(res,'Supernet',             self._sp_snet_v, color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Prefix Length',        self._sp_pfx_v,  lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Supernet Mask',        self._sp_mask_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total Addresses',      self._sp_hosts_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Subnets Entered',      self._sp_nets_v, lbl_fs=10,val_fs=11,row_h=34)

    def _calc_supernet(self):
        try:
            import ipaddress as _ip
            raws = [self._sp_n1.get(),self._sp_n2.get(),
                    self._sp_n3.get(),self._sp_n4.get()]
            networks = [_ip.IPv4Network(r.strip(),strict=False) for r in raws if r.strip()]
            if not networks: raise ValueError('Enter at least one subnet')
            # Find smallest supernet covering all
            min_ip = min(int(n.network_address) for n in networks)
            max_ip = max(int(n.broadcast_address) for n in networks)
            diff   = min_ip ^ max_ip
            prefix = 32 - (diff.bit_length() if diff else 0)
            mask   = (~((1<<(32-prefix))-1)) & 0xFFFFFFFF
            snet   = _ip.IPv4Network(f'{_ip.IPv4Address(min_ip & mask)}/{prefix}',strict=False)
            self._sp_snet_v.set(str(snet))
            self._sp_pfx_v.set(f'/{snet.prefixlen}')
            self._sp_mask_v.set(str(snet.netmask))
            self._sp_hosts_v.set(f'{snet.num_addresses:,}')
            self._sp_nets_v.set(str(len(networks)))
        except Exception as e:
            self._sp_snet_v.set(f'Error: {e}')

    def _clear_supernet(self):
        for v in [self._sp_n1,self._sp_n2,self._sp_n3,self._sp_n4]: v.set('')
        for v in [self._sp_snet_v,self._sp_pfx_v,self._sp_mask_v,
                  self._sp_hosts_v,self._sp_nets_v]: v.set('—')

    def _sample_supernet(self):
        self._sp_n1.set('192.168.0.0/24'); self._sp_n2.set('192.168.1.0/24')
        self._sp_n3.set('192.168.2.0/24'); self._sp_n4.set('192.168.3.0/24')

    # ── IP CONVERTER ─────────────────────────────────────────────────────
    def _build_ipconv(self):
        tab = self._all_frames["IP Converter"]
        ctk.CTkLabel(tab, text="IP Converter",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(inner, text="Enter IP in any format: dotted (192.168.1.1), integer, or hex (0xC0A80101)",
                     font=ctk.CTkFont("Segoe UI",9), text_color=MUTED, anchor='w').pack(anchor='w',padx=16,pady=(8,2))
        self._ic_input = labeled_entry(inner,'IP Address','192.168.1.1', on_enter=self._calculate)
        calc_button(tab,'Convert →',self._calc_ipconv,
                    clear_cmd=self._clear_ipconv,sample_cmd=self._sample_ipconv)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._ic_dec_v = tk.StringVar(value='—'); self._ic_bin_v  = tk.StringVar(value='—')
        self._ic_hex_v = tk.StringVar(value='—'); self._ic_int_v  = tk.StringVar(value='—')
        self._ic_cls_v = tk.StringVar(value='—'); self._ic_typ_v  = tk.StringVar(value='—')
        result_row(res,'Dotted Decimal',   self._ic_dec_v,color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Binary (octets)',  self._ic_bin_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Hexadecimal',      self._ic_hex_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Integer',          self._ic_int_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'IP Class',         self._ic_cls_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Address Type',     self._ic_typ_v,lbl_fs=10,val_fs=11,row_h=34)

    def _calc_ipconv(self):
        try:
            import ipaddress as _ip
            raw = self._ic_input.get().strip()
            if raw.startswith('0x') or raw.startswith('0X'):
                addr = _ip.IPv4Address(int(raw, 16))
            elif '.' in raw:
                addr = _ip.IPv4Address(raw)
            else:
                addr = _ip.IPv4Address(int(raw))
            iv   = int(addr)
            octs = str(addr).split('.')
            bins = '.'.join(f'{int(o):08b}' for o in octs)
            fo   = int(octs[0])
            cls  = ('A' if fo<128 else 'B' if fo<192 else 'C' if fo<224
                    else 'D (Multicast)' if fo<240 else 'E (Experimental)')
            typ  = ('Loopback' if addr.is_loopback else
                    'Private'  if addr.is_private  else
                    'Multicast' if addr.is_multicast else
                    'Link-local' if addr.is_link_local else 'Public / Global')
            self._ic_dec_v.set(str(addr))
            self._ic_bin_v.set(bins)
            self._ic_hex_v.set(hex(iv).upper().replace('X','x'))
            self._ic_int_v.set(f'{iv:,}')
            self._ic_cls_v.set(f'Class {cls}')
            self._ic_typ_v.set(typ)
        except Exception as e:
            self._ic_dec_v.set(f'Error: {e}')

    def _clear_ipconv(self):
        self._ic_input.set('')
        for v in [self._ic_dec_v,self._ic_bin_v,self._ic_hex_v,
                  self._ic_int_v,self._ic_cls_v,self._ic_typ_v]: v.set('—')

    def _sample_ipconv(self):
        self._ic_input.set('192.168.1.1')

    def _build_binhex(self):
        t=BinaryHexCalcTab(self._all_frames["Binary-Hex"])
        t.pack(fill="both",expand=True); self._bh_inst=t

    def _calc_binhex(self):
        if hasattr(self,"_bh_inst"): self._bh_inst._calculate()

    def _build_cheatsheet(self):
        t=SubnetCheatsheetTab(self._all_frames["Subnet Cheat Sheet"])
        t.pack(fill="both",expand=True)

    def _build_ipv6(self):
        t=IPv6CalcTab(self._all_frames["IPv6 Calculator"])
        t.pack(fill="both",expand=True); self._v6_inst=t

    def _calc_ipv6(self):
        if hasattr(self,"_v6_inst"): self._v6_inst._calculate()




class SavingsGoalCalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG); self._build()

    def _calculate(self):
        try:
            import math as _m
            target  = float(self._sg_target.get())
            current = float(self._sg_current.get())
            rate    = float(self._sg_rate.get()) / 100 / 12   # monthly
            months  = float(self._sg_yrs.get()) * 12
            if months <= 0: raise ValueError('years must be > 0')
            fv_current = current * (1 + rate)**months
            remaining  = target - fv_current
            if rate > 0:
                pmt = remaining * rate / ((1 + rate)**months - 1)
            else:
                pmt = remaining / months
            total_pmt  = pmt * months
            interest   = target - current - total_pmt
            self._sg_pmt_v.set(f'${pmt:,.2f}/month')
            self._sg_totc_v.set(f'${total_pmt:,.2f}')
            self._sg_int_v.set(f'${interest:,.2f}')
            self._sg_pct_v.set(f'{total_pmt/target*100:.1f}% contributed,  {interest/target*100:.1f}% interest')
        except Exception as e:
            self._sg_pmt_v.set(f'Error: {e}')

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._sg_target  = labeled_entry(inner, 'Savings Goal ($)', '100000', on_enter=self._calculate)
        self._sg_current = labeled_entry(inner, 'Current Savings ($)', '5000', on_enter=self._calculate)
        self._sg_rate    = labeled_entry(inner, 'Annual Return (%)', '7.0', on_enter=self._calculate)
        self._sg_yrs     = labeled_entry(inner, 'Years to Goal', '20', on_enter=self._calculate)
        calc_button(self, 'Calculate →', self._calculate,
                    clear_cmd=self._clear, sample_cmd=self._sample)
        res = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._sg_pmt_v  = tk.StringVar(value='—'); self._sg_totc_v = tk.StringVar(value='—')
        self._sg_int_v  = tk.StringVar(value='—'); self._sg_pct_v  = tk.StringVar(value='—')
        result_row(res,'Monthly Contribution Needed', self._sg_pmt_v, color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total Contributions',         self._sg_totc_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Interest Earned',             self._sg_int_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Contribution vs Interest',    self._sg_pct_v, lbl_fs=10,val_fs=11,row_h=34)

    def _clear(self):
        for v in [self._sg_target,self._sg_current,self._sg_rate,self._sg_yrs]: v.set('')
        for v in [self._sg_pmt_v,self._sg_totc_v,self._sg_int_v,self._sg_pct_v]: v.set('—')

    def _sample(self):
        self._sg_target.set('100000'); self._sg_current.set('5000')
        self._sg_rate.set('7.0');      self._sg_yrs.set('20')

class CreditCardCalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG); self._build()

    def _calculate(self):
        try:
            import math as _m
            bal  = float(self._cc_bal.get())
            apr  = float(self._cc_apr.get()) / 100 / 12
            pmt  = float(self._cc_pmt.get())
            monthly_interest = bal * apr
            if pmt <= monthly_interest:
                raise ValueError(
                    f'Monthly payment ${pmt:.2f} must exceed '
                    f'monthly interest ${monthly_interest:.2f}\n'
                    f'(balance × APR/12). Increase your payment.')
            months   = -_m.log(1 - apr*bal/pmt) / _m.log(1+apr)
            total    = pmt * months
            interest = total - bal
            # Min payment: use entered value if provided, else estimate (2% or $25)
            raw_min = self._cc_minpmt.get().strip()
            if raw_min:
                min_pmt = float(raw_min)
            else:
                min_pmt = max(25.0, bal * 0.02)
            if min_pmt > bal * apr:
                min_m   = -_m.log(1 - apr*bal/min_pmt) / _m.log(1+apr)
                min_int = min_pmt * min_m - bal
            else:
                min_m = float('inf'); min_int = float('inf')
            self._cc_mths_v.set(f'{months:.1f} months  ({months/12:.1f} yrs)')
            self._cc_tot_v.set(f'${total:,.2f}')
            self._cc_int_v.set(f'${interest:,.2f}')
            if min_int != float('inf'):
                saved = min_int - interest
                label = '(entered)' if raw_min else '(estimated 2% or $25)'
                self._cc_save_v.set(f'${saved:,.2f} saved  {label}')
                self._cc_min_v.set(f'${min_pmt:.2f}/mo  →  {min_m/12:.0f} yrs  /  ${min_int:,.0f} interest')
            else:
                self._cc_save_v.set('N/A — min payment too low')
                self._cc_min_v.set('N/A')
        except Exception as e:
            self._cc_mths_v.set(f'Error: {e}')

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._cc_bal    = labeled_entry(inner, 'Balance ($)', '5000', on_enter=self._calculate)
        self._cc_apr    = labeled_entry(inner, 'APR (%)', '19.99', on_enter=self._calculate)
        self._cc_pmt    = labeled_entry(inner, 'Monthly Payment ($)', '200', on_enter=self._calculate)
        self._cc_minpmt = labeled_entry(inner, 'Min Payment ($)  optional — leave blank to estimate', '', on_enter=self._calculate)
        calc_button(self, 'Calculate →', self._calculate,
                    clear_cmd=self._clear, sample_cmd=self._sample)
        res = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._cc_mths_v = tk.StringVar(value='—'); self._cc_tot_v  = tk.StringVar(value='—')
        self._cc_int_v  = tk.StringVar(value='—'); self._cc_save_v = tk.StringVar(value='—')
        self._cc_min_v  = tk.StringVar(value='—')
        result_row(res,'Payoff Time',           self._cc_mths_v,color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total Paid',            self._cc_tot_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total Interest',        self._cc_int_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Interest Saved vs Min', self._cc_save_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Min Payment Scenario',  self._cc_min_v, lbl_fs=10,val_fs=11,row_h=34)

    def _clear(self):
        for v in [self._cc_bal,self._cc_apr,self._cc_pmt,self._cc_minpmt]: v.set('')
        for v in [self._cc_mths_v,self._cc_tot_v,self._cc_int_v,self._cc_save_v,self._cc_min_v]: v.set('—')

    def _sample(self):
        self._cc_bal.set('5000'); self._cc_apr.set('19.99')
        self._cc_pmt.set('200');  self._cc_minpmt.set('')


# ─────────────────────────────────────────────────────────────────────────────
# IT NETWORKING: Binary-Hex, Subnet Cheatsheet, IPv6
# ─────────────────────────────────────────────────────────────────────────────

class BinaryHexCalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG); self._build()

    def _calculate(self):
        try:
            raw  = self._bh_val.get().strip().replace(' ','').replace('.','')
            base = {'Decimal':10,'Binary':2,'Hexadecimal':16,'Octal':8}.get(self._bh_base.get(),10)
            n    = int(raw, base)
            if n < 0 or n > 0xFFFFFFFF: raise ValueError('Value must be 0–4294967295')
            self._bh_dec_v.set(f'{n:,}')
            self._bh_hex_v.set(f'0x{n:08X}')
            self._bh_oct_v.set(f'0o{n:011o}')
            self._bh_8_v.set(f'{n:08b}')
            self._bh_16_v.set(f'{n>>16:016b}  {n&0xFFFF:016b}'[:35] if n>0xFFFF else f'{n:016b}')
            self._bh_32_v.set(f'{n:032b}')
            # Bitwise ops with second value
            raw2 = self._bh_val2.get().strip().replace(' ','').replace('.','')
            if raw2:
                n2 = int(raw2, base)
                and_r = n & n2; or_r = n | n2; xor_r = n ^ n2
                not_r = (~n) & 0xFFFFFFFF
                self._bh_and_v.set(f'{and_r}  (0x{and_r:X})')
                self._bh_or_v.set(f'{or_r}  (0x{or_r:X})')
                self._bh_xor_v.set(f'{xor_r}  (0x{xor_r:X})')
                self._bh_not_v.set(f'{not_r}  (0x{not_r:X})')
                self._bh_shl_v.set(f'{(n<<1)&0xFFFFFFFF}  (0x{(n<<1)&0xFFFFFFFF:X})')
                self._bh_shr_v.set(f'{n>>1}  (0x{n>>1:X})')
            else:
                for v in [self._bh_and_v,self._bh_or_v,self._bh_xor_v,
                          self._bh_not_v,self._bh_shl_v,self._bh_shr_v]: v.set('—')
        except Exception as e:
            self._bh_dec_v.set(f'Error: {e}')

    def _build(self):
        ctk.CTkLabel(self, text="Binary / Hex Converter",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._bh_val  = labeled_entry(inner,'Value (A)', '255', on_enter=self._calculate)
        self._bh_base = labeled_option(inner,'Input Base',
                                       ['Decimal','Binary','Hexadecimal','Octal'],
                                       default='Decimal')
        self._bh_val2 = labeled_entry(inner,'Value B (bitwise ops)', '170', on_enter=self._calculate)
        calc_button(self,'Calculate →',self._calculate,
                    clear_cmd=self._clear,sample_cmd=self._sample)
        # Conversion results
        r1 = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        r1.pack(fill='x', padx=20, pady=(0,4))
        ctk.CTkLabel(r1,text='Number Conversion',font=ctk.CTkFont('Segoe UI',10,'bold'),
                     text_color=TEXT).pack(anchor='w',padx=12,pady=(6,2))
        self._bh_dec_v=tk.StringVar(value='—'); self._bh_hex_v=tk.StringVar(value='—')
        self._bh_oct_v=tk.StringVar(value='—'); self._bh_8_v  =tk.StringVar(value='—')
        self._bh_16_v =tk.StringVar(value='—'); self._bh_32_v =tk.StringVar(value='—')
        result_row(r1,'Decimal',     self._bh_dec_v,color=ACCENT,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r1,'Hexadecimal', self._bh_hex_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r1,'Octal',       self._bh_oct_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r1,'8-bit Binary',self._bh_8_v,  lbl_fs=10,val_fs=11,row_h=32)
        result_row(r1,'16-bit',      self._bh_16_v, lbl_fs=10,val_fs=11,row_h=32)
        result_row(r1,'32-bit',      self._bh_32_v, lbl_fs=10,val_fs=11,row_h=32)
        # Bitwise results
        r2 = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        r2.pack(fill='x', padx=20, pady=(4,8))
        ctk.CTkLabel(r2,text='Bitwise Operations  (A and B)',font=ctk.CTkFont('Segoe UI',10,'bold'),
                     text_color=TEXT).pack(anchor='w',padx=12,pady=(6,2))
        self._bh_and_v=tk.StringVar(value='—'); self._bh_or_v =tk.StringVar(value='—')
        self._bh_xor_v=tk.StringVar(value='—'); self._bh_not_v=tk.StringVar(value='—')
        self._bh_shl_v=tk.StringVar(value='—'); self._bh_shr_v=tk.StringVar(value='—')
        result_row(r2,'A AND B',  self._bh_and_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r2,'A OR B',   self._bh_or_v, lbl_fs=10,val_fs=11,row_h=32)
        result_row(r2,'A XOR B',  self._bh_xor_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r2,'NOT A',    self._bh_not_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r2,'A << 1',   self._bh_shl_v,lbl_fs=10,val_fs=11,row_h=32)
        result_row(r2,'A >> 1',   self._bh_shr_v,lbl_fs=10,val_fs=11,row_h=32)

    def _clear(self):
        self._bh_val.set(''); self._bh_val2.set('')
        for v in [self._bh_dec_v,self._bh_hex_v,self._bh_oct_v,self._bh_8_v,
                  self._bh_16_v,self._bh_32_v,self._bh_and_v,self._bh_or_v,
                  self._bh_xor_v,self._bh_not_v,self._bh_shl_v,self._bh_shr_v]: v.set('—')

    def _sample(self):
        self._bh_val.set('255'); self._bh_base.set('Decimal'); self._bh_val2.set('170')

class IPv6CalcTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG); self._build()

    def _calculate(self):
        try:
            import ipaddress as _ip
            inp = self._v6_input.get().strip()
            if '/' in inp:
                net  = _ip.IPv6Network(inp, strict=False)
                addr = _ip.IPv6Address(inp.split('/')[0])
            else:
                net  = None
                addr = _ip.IPv6Address(inp)
            typ = ('Loopback' if addr.is_loopback else
                   'Link-local' if addr.is_link_local else
                   'Multicast' if addr.is_multicast else
                   'Private/ULA' if addr.is_private else
                   'Global Unicast')
            self._v6_full_v.set(addr.exploded)
            self._v6_comp_v.set(str(addr))
            if net:
                self._v6_net_v.set(str(net.network_address))
                self._v6_pfx_v.set(f'/{net.prefixlen}')
                self._v6_tot_v.set(f'{net.num_addresses:,}')
            else:
                self._v6_net_v.set('N/A — no prefix given')
                self._v6_pfx_v.set('N/A'); self._v6_tot_v.set('N/A')
            self._v6_typ_v.set(typ)
            self._v6_ver_v.set('IPv6 (128-bit)')
        except Exception as e:
            self._v6_full_v.set(f'Error: {e}')

    def _build(self):
        ctk.CTkLabel(self, text="IPv6 Calculator",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        inner = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(inner, text='Enter IPv6 address  e.g.  2001:db8::1  or  2001:db8::/32',
                     font=ctk.CTkFont('Segoe UI',9), text_color=MUTED,
                     anchor='w').pack(anchor='w',padx=16,pady=(8,2))
        self._v6_input = labeled_entry(inner,'IPv6 Address / CIDR','2001:db8::1', on_enter=self._calculate)
        calc_button(self,'Calculate →',self._calculate,
                    clear_cmd=self._clear,sample_cmd=self._sample)
        res = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._v6_full_v=tk.StringVar(value='—'); self._v6_comp_v=tk.StringVar(value='—')
        self._v6_net_v =tk.StringVar(value='—'); self._v6_pfx_v =tk.StringVar(value='—')
        self._v6_tot_v =tk.StringVar(value='—'); self._v6_typ_v =tk.StringVar(value='—')
        self._v6_ver_v =tk.StringVar(value='—')
        result_row(res,'Full Expanded Form', self._v6_full_v,color=ACCENT,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Compressed Form',    self._v6_comp_v,lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Network Address',    self._v6_net_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Prefix',             self._v6_pfx_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Total Addresses',    self._v6_tot_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Address Type',       self._v6_typ_v, lbl_fs=10,val_fs=11,row_h=34)
        result_row(res,'Version',            self._v6_ver_v, lbl_fs=10,val_fs=11,row_h=34)

    def _clear(self):
        self._v6_input.set('')
        for v in [self._v6_full_v,self._v6_comp_v,self._v6_net_v,
                  self._v6_pfx_v,self._v6_tot_v,self._v6_typ_v,self._v6_ver_v]: v.set('—')

    def _sample(self):
        self._v6_input.set('2001:db8::/32')

class SubnetCheatsheetTab(ctk.CTkScrollableFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Subnet Cheat Sheet",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        def hdr(txt):
            ctk.CTkLabel(self, text=txt, font=ctk.CTkFont('Segoe UI',14,'bold'),
                         text_color=TEXT, anchor='w').pack(fill='x',padx=16,pady=(12,2))

        def row(cols, fg=CARD):
            r = ctk.CTkFrame(self, fg_color=fg, corner_radius=0)
            r.pack(fill='x', padx=16, pady=1)
            for i,col in enumerate(cols):
                w = [80,140,120,110][i] if i<4 else 100
                ctk.CTkLabel(r, text=col, font=ctk.CTkFont('Segoe UI',11),
                             text_color=TEXT, width=w, anchor='w'
                             ).pack(side='left', padx=(8,0), pady=4)

        # CIDR Reference
        hdr('CIDR / Subnet Mask Quick Reference')
        row(['CIDR','Subnet Mask','Wildcard','Hosts','Subnets of /8'], fg=RES_BG)
        data = [
            ('/8', '255.0.0.0', '0.255.255.255', '16,777,214', '1'),
            ('/9', '255.128.0.0', '0.127.255.255', '8,388,606', '2'),
            ('/10','255.192.0.0','0.63.255.255','4,194,302','4'),
            ('/12','255.240.0.0','0.15.255.255','1,048,574','16'),
            ('/16','255.255.0.0','0.0.255.255','65,534','256'),
            ('/17','255.255.128.0','0.0.127.255','32,766','512'),
            ('/20','255.255.240.0','0.0.15.255','4,094','4,096'),
            ('/22','255.255.252.0','0.0.3.255','1,022','16,384'),
            ('/24','255.255.255.0','0.0.0.255','254','16.7M'),
            ('/25','255.255.255.128','0.0.0.127','126','33.5M'),
            ('/26','255.255.255.192','0.0.0.63','62','67M'),
            ('/27','255.255.255.224','0.0.0.31','30','134M'),
            ('/28','255.255.255.240','0.0.0.15','14','268M'),
            ('/29','255.255.255.248','0.0.0.7','6','536M'),
            ('/30','255.255.255.252','0.0.0.3','2','1.07B'),
            ('/31','255.255.255.254','0.0.0.1','0 (P2P)','—'),
            ('/32','255.255.255.255','0.0.0.0','1 (host)','—'),
        ]
        for i,d in enumerate(data):
            row(d, fg=CARD if i%2==0 else INPUT_BG)

        # Private Ranges
        hdr('Private IP Address Ranges  (RFC 1918)')
        row(['Range','CIDR','Addresses','Use Case'], fg=RES_BG)
        priv = [
            ('10.0.0.0 – 10.255.255.255','10.0.0.0/8','16.7 million','Large enterprise'),
            ('172.16.0.0 – 172.31.255.255','172.16.0.0/12','1 million','Medium networks'),
            ('192.168.0.0 – 192.168.255.255','192.168.0.0/16','65,536','Home / SOHO'),
        ]
        for i,d in enumerate(priv):
            row(d, fg=CARD if i%2==0 else INPUT_BG)

        # Special Addresses
        hdr('Special / Reserved Addresses')
        row(['Address / Range','Purpose'], fg=RES_BG)
        spec = [
            ('127.0.0.0/8','Loopback (localhost = 127.0.0.1)'),
            ('169.254.0.0/16','APIPA / Link-local (no DHCP)'),
            ('224.0.0.0/4','Multicast (Class D)'),
            ('240.0.0.0/4','Reserved (Class E — experimental)'),
            ('255.255.255.255','Limited broadcast (all networks)'),
            ('0.0.0.0','Unspecified / default route'),
        ]
        for i,d in enumerate(spec):
            row(d, fg=CARD if i%2==0 else INPUT_BG)

        # IPv6 Quick Reference
        hdr('IPv6 Common Prefixes')
        row(['Prefix','Type / Purpose'], fg=RES_BG)
        v6 = [
            ('::1/128','Loopback (equivalent of 127.0.0.1)'),
            ('fe80::/10','Link-local (auto-configured, not routable)'),
            ('fc00::/7','Unique Local (private, RFC 4193)'),
            ('ff00::/8','Multicast'),
            ('2000::/3','Global Unicast (public internet)'),
            ('2001:db8::/32','Documentation / examples (RFC 3849)'),
            ('::ffff:0:0/96','IPv4-mapped IPv6 addresses'),
        ]
        for i,d in enumerate(v6):
            row(d, fg=CARD if i%2==0 else INPUT_BG)
# ─────────────────────────────────────────────────────────
# BILL SPLITTER
# ─────────────────────────────────────────────────────────

class BillSplitterTab(CalcTabMixin, ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._custom_pct_vars = []
        self._custom_res_vars = []
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Bill Splitter",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Split a bill equally or by custom percentages — tip included.",
                 font=("Segoe UI", 9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0, 10))

        # ── Top two-column layout ──────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        # LEFT — inputs
        left = make_card(top)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        section_header(left, "  BILL DETAILS")
        inp = ctk.CTkFrame(left, fg_color="transparent")
        inp.pack(fill="x", padx=16, pady=(0, 8))
        self.bs_amount  = labeled_entry(inp, "Bill Amount ($)", "100.00", on_enter=self._calculate)
        self.bs_tip_pct = labeled_entry(inp, "Tip (%)",         "15",     on_enter=self._calculate)
        self.bs_people  = labeled_entry(inp, "Number of People","2",      on_enter=self._calculate)

        section_header(left, "  SPLIT METHOD")
        mf = ctk.CTkFrame(left, fg_color="transparent")
        mf.pack(fill="x", padx=16, pady=(0, 8))
        self.bs_method = tk.StringVar(value="Equal")
        for lbl, val in [("Split Equally", "Equal"), ("Custom Percentages", "Custom")]:
            ctk.CTkRadioButton(mf, text=lbl, variable=self.bs_method, value=val,
                               command=self._toggle_method,
                               font=ctk.CTkFont("Segoe UI", 12), text_color=TEXT,
                               fg_color=ACCENT, hover_color=NAV_ACT
                               ).pack(anchor="w", pady=3)

        calc_button(left, "Calculate →", self._calculate,
                    clear_cmd=self._clear, sample_cmd=self._sample)

        # RIGHT — results
        right = make_card(top)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        section_header(right, "  RESULTS")
        res = ctk.CTkFrame(right, fg_color="transparent")
        res.pack(fill="x", padx=16, pady=(0, 16))
        self.bs_tip_amt = tk.StringVar(value="—")
        self.bs_grand   = tk.StringVar(value="—")
        self.bs_sub_pp  = tk.StringVar(value="—")
        self.bs_tip_pp  = tk.StringVar(value="—")
        self.bs_tot_pp  = tk.StringVar(value="—")
        result_row(res, "Tip Amount",  self.bs_tip_amt)
        result_row(res, "Grand Total", self.bs_grand, color=ACCENT)
        ctk.CTkFrame(res, height=1, fg_color=BORDER).pack(fill="x", pady=8)
        ctk.CTkLabel(res, text="Per Person  (Equal Split)",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=MUTED).pack(anchor="w", pady=(0, 4))
        result_row(res, "Subtotal", self.bs_sub_pp)
        result_row(res, "Tip",      self.bs_tip_pp)
        result_row(res, "Total",    self.bs_tot_pp, color=ACCENT)

        # ── Custom % section (hidden until Custom selected) ────────────────
        self.bs_custom_card = make_card(self)
        section_header(self.bs_custom_card, "  CUSTOM SPLIT")
        ctk.CTkLabel(self.bs_custom_card,
                     text="Enter each person’s share. Percentages must add up to 100%.",
                     font=ctk.CTkFont("Segoe UI", 10), text_color=MUTED
                     ).pack(anchor="w", padx=16, pady=(0, 2))
        self.bs_pct_lbl = ctk.CTkLabel(self.bs_custom_card, text="Total: 0%",
                                        font=ctk.CTkFont("Segoe UI", 11, "bold"),
                                        text_color=ACCENT)
        self.bs_pct_lbl.pack(anchor="e", padx=16, pady=(0, 4))
        self.bs_custom_sf = ctk.CTkScrollableFrame(
            self.bs_custom_card, fg_color="transparent", height=160)
        self.bs_custom_sf.pack(fill="x", padx=16, pady=(0, 12))

        # ── Quick tip reference ────────────────────────────────────────────
        tip_card = make_card(self)
        tip_card.pack(fill="x", padx=20, pady=(10, 12))
        section_header(tip_card, "  QUICK TIP REFERENCE")
        ctk.CTkLabel(tip_card, text="Based on current bill amount",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(0, 4))
        ref_row = ctk.CTkFrame(tip_card, fg_color="transparent")
        ref_row.pack(fill="x", padx=16, pady=(0, 12))
        self.bs_ref_vars = {}
        for pct in [5, 10, 15, 18, 20]:
            cell = ctk.CTkFrame(ref_row, fg_color=INPUT_BG, corner_radius=10,
                                border_width=1, border_color=BORDER)
            cell.pack(side="left", expand=True, fill="x", padx=4)
            ctk.CTkLabel(cell, text=f"{pct}%",
                         font=ctk.CTkFont("Segoe UI", 14, "bold"),
                         text_color=ACCENT).pack(pady=(10, 2))
            v = tk.StringVar(value="—")
            self.bs_ref_vars[pct] = v
            ctk.CTkLabel(cell, textvariable=v,
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=TEXT).pack(pady=(0, 10))

    def _toggle_method(self):
        if self.bs_method.get() == "Custom":
            self.bs_custom_card.pack(fill="x", padx=20, pady=(10, 0))
            self._rebuild_custom_rows()
        else:
            self.bs_custom_card.pack_forget()

    def _rebuild_custom_rows(self):
        for w in self.bs_custom_sf.winfo_children():
            w.destroy()
        self._custom_pct_vars.clear()
        self._custom_res_vars.clear()
        try:
            n = max(1, min(20, int(self.bs_people.get())))
        except Exception:
            n = 2
        equal_pct = round(100 / n, 1)
        remainder = round(100.0 - equal_pct * n, 1)  # carry for rounding
        for i in range(n):
            row = ctk.CTkFrame(self.bs_custom_sf, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"Person {i + 1}:",
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=TEXT, width=80, anchor="w").pack(side="left")
            # Person 1 absorbs any rounding remainder so total = 100%
            pct_val = round(equal_pct + remainder, 1) if (i == 0 and remainder != 0) else equal_pct
            pv = tk.StringVar(value=str(pct_val))
            self._custom_pct_vars.append(pv)
            pv.trace_add("write", lambda *_: (self._update_pct_total(),
                                               self._calculate()))
            ctk.CTkEntry(row, textvariable=pv, width=70,
                         fg_color=INPUT_BG, border_color=INPUT_BORDER,
                         font=ctk.CTkFont("Segoe UI", 11)).pack(side="left", padx=(4, 2))
            ctk.CTkLabel(row, text="%",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=MUTED).pack(side="left", padx=(0, 12))
            rv = tk.StringVar(value="—")
            self._custom_res_vars.append(rv)
            ctk.CTkLabel(row, textvariable=rv,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color=ACCENT).pack(side="left")
        self._update_pct_total()

    def _update_pct_total(self):
        try:
            total = sum(float(v.get() or 0) for v in self._custom_pct_vars)
            color = SUCCESS if abs(total - 100) < 0.01 else "#C53030"
            self.bs_pct_lbl.configure(text=f"Total: {total:.1f}%", text_color=color)
        except Exception:
            pass

    def _clear(self):
        self.bs_amount.set(""); self.bs_tip_pct.set(""); self.bs_people.set("")
        for v in [self.bs_tip_amt, self.bs_grand, self.bs_sub_pp,
                  self.bs_tip_pp, self.bs_tot_pp]:
            v.set("—")
        for v in self.bs_ref_vars.values():
            v.set("—")
        for rv in self._custom_res_vars:
            rv.set("—")

    def _sample(self):
        self.bs_amount.set("120.00")
        self.bs_tip_pct.set("18")
        self.bs_people.set("4")

    def _calculate(self):
        try:
            amount  = float(self.bs_amount.get().replace(",", ""))
            tip_pct = float(self.bs_tip_pct.get())
            n       = max(1, int(self.bs_people.get()))
            tip_amt = amount * tip_pct / 100
            grand   = amount + tip_amt
            self.bs_tip_amt.set(fmt_currency(tip_amt))
            self.bs_grand.set(fmt_currency(grand))
            self.bs_sub_pp.set(fmt_currency(amount / n))
            self.bs_tip_pp.set(fmt_currency(tip_amt / n))
            self.bs_tot_pp.set(fmt_currency(grand / n))
            for pct, var in self.bs_ref_vars.items():
                var.set(fmt_currency(amount * pct / 100))
            if self.bs_method.get() == "Custom":
                # Rebuild rows if person count changed since last toggle
                if len(self._custom_pct_vars) != n:
                    self._rebuild_custom_rows()
                for pv, rv in zip(self._custom_pct_vars, self._custom_res_vars):
                    try:
                        share   = float(pv.get()) / 100
                        sub_s   = amount * share
                        tip_s   = tip_amt * share
                        rv.set(f"${sub_s:.2f}  +  ${tip_s:.2f} tip  =  ${sub_s + tip_s:.2f}")
                    except Exception:
                        rv.set("—")
        except Exception as e:
            self.bs_tip_amt.set(f"Error: {e}")


class FinanceCalcTab(CalcTabMixin, ctk.CTkFrame):

    ALL_CALCS = [
        "Amortization", "Bill Splitter", "Compound Interest", "Credit Card Payoff",
        "Depreciation", "Loan", "MACRS Full", "MACRS Rate", "Mortgage",
        "ROI", "Savings Goal"
    ]

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}
        self._calc_insts  = {}
        self._active_calc = self.ALL_CALCS[0]
        self._build()

    def _calculate(self):
        inst = self._calc_insts.get(self._active_calc)
        if inst and hasattr(inst, "_calculate"):
            inst._calculate()

    def show_calculator(self, name):
        for f in self._all_frames.values():
            f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    def _build(self):
        _cls = {
            "Loan":               LoanCalcTab,
            "Depreciation":       BasicDepreciationTab,
            "MACRS Rate":         MacrsRateTab,
            "MACRS Full":         MacrsFullTab,
            "Mortgage":           MortgageTab,
            "Amortization":       AmortizationTab,
            "Compound Interest":  CompoundInterestCalcTab,
            "ROI":                ROICalcTab,
            "Savings Goal":       SavingsGoalCalcTab,
            "Bill Splitter":      BillSplitterTab,
            "Credit Card Payoff": CreditCardCalcTab,
        }
        for name in self.ALL_CALCS:
            frame = ctk.CTkFrame(self, fg_color=APP_BG)
            self._all_frames[name] = frame
            inst = _cls[name](frame)
            inst.pack(fill="both", expand=True)
            self._calc_insts[name] = inst
        self.show_calculator(self.ALL_CALCS[0])


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSION TAB
# ═══════════════════════════════════════════════════════════════════════════════
class ConversionCalcTab(CalcTabMixin, ctk.CTkFrame):

    ALL_CALCS = ["Currency", "Time & Date", "Unit Converter"]

    _UNITS = {
        "Length":    {"Meter":1,"Kilometer":1000,"Centimeter":0.01,"Millimeter":0.001,
                      "Inch":0.0254,"Foot":0.3048,"Yard":0.9144,"Mile":1609.344,"Nautical Mile":1852},
        "Weight":    {"Kilogram":1,"Gram":0.001,"Milligram":1e-6,"Pound":0.453592,
                      "Ounce":0.0283495,"Metric Ton":1000,"US Ton":907.185},
        "Volume":    {"Liter":1,"Milliliter":0.001,"Cubic Meter":1000,"Gallon (US)":3.78541,
                      "Gallon (UK)":4.54609,"Fl Oz (US)":0.0295735,"Cup":0.236588,"Pint":0.473176},
        "Area":      {"Sq Meter":1,"Sq Kilometer":1e6,"Sq Foot":0.0929,"Sq Inch":0.000645,
                      "Acre":4046.86,"Hectare":10000},
        "Speed":     {"m/s":1,"km/h":1/3.6,"mph":0.44704,"Knot":0.514444,"ft/s":0.3048},
        "Pressure":  {"Pascal":1,"Bar":100000,"PSI":6894.76,"Atmosphere":101325,
                      "mmHg":133.322,"kPa":1000},
        "Temperature":{"Celsius":"C","Fahrenheit":"F","Kelvin":"K"},
        "Data":      {"Bit":0.125,"Byte":1,"Kilobyte":1024,"Megabyte":1048576,
                      "Gigabyte":1073741824,"Terabyte":1099511627776},
    }

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}
        self._active_calc = self.ALL_CALCS[0]
        self._build()

    def _calculate(self):
        fn = {"Currency":     self._calc_currency,
              "Time & Date":  self._calc_timedate,
              "Unit Converter":self._calc_units}.get(self._active_calc)
        if fn: fn()

    def show_calculator(self, name):
        for f in self._all_frames.values(): f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    def _build(self):
        for name in self.ALL_CALCS:
            self._all_frames[name] = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._build_currency()
        self._build_timedate()
        self._build_units()
        self.show_calculator(self.ALL_CALCS[0])

    # ── UNIT CONVERTER ──────────────────────────────────────────────────────
    def _build_units(self):
        tab = self._all_frames["Unit Converter"]
        ctk.CTkLabel(tab, text="Unit Converter",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Overwrite the sample data",
                 font=("Segoe UI",9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        cats = list(self._UNITS.keys())
        self._uc_cat    = labeled_option(inner,'Category', cats, default='Length')
        # From/To units — built manually so we can reconfigure values on category change
        _frow = ctk.CTkFrame(inner, fg_color="transparent"); _frow.pack(fill="x", pady=3)
        ctk.CTkLabel(_frow, text="From Unit", font=ctk.CTkFont("Segoe UI",10),
                     text_color=TEXT, width=220, anchor="w").pack(side="left")
        self._uc_from = tk.StringVar(value="Foot")
        self._uc_from_menu = ctk.CTkOptionMenu(_frow, variable=self._uc_from,
            values=list(self._UNITS["Length"].keys()), width=160,
            fg_color=INPUT_BG, button_color=ACCENT, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI",10))
        self._uc_from_menu.pack(side="left", padx=(8,0))
        _trow = ctk.CTkFrame(inner, fg_color="transparent"); _trow.pack(fill="x", pady=3)
        ctk.CTkLabel(_trow, text="To Unit", font=ctk.CTkFont("Segoe UI",10),
                     text_color=TEXT, width=220, anchor="w").pack(side="left")
        self._uc_to = tk.StringVar(value="Meter")
        self._uc_to_menu = ctk.CTkOptionMenu(_trow, variable=self._uc_to,
            values=list(self._UNITS["Length"].keys()), width=160,
            fg_color=INPUT_BG, button_color=ACCENT, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI",10))
        self._uc_to_menu.pack(side="left", padx=(8,0))
        self._uc_val    = labeled_entry(inner,'Value','1', on_enter=self._calc_units)
        # Wire category change
        self._uc_cat.trace_add('write', lambda *_: self._on_uc_cat_change())
        calc_button(tab,'Convert →',self._calc_units,
                    clear_cmd=self._clear_units, sample_cmd=self._sample_units)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._uc_result_v = tk.StringVar(value='—')
        self._uc_factor_v = tk.StringVar(value='—')
        result_row(res,'Result',             self._uc_result_v, color=ACCENT, lbl_fs=10, val_fs=11, row_h=38)
        result_row(res,'Conversion Factor',  self._uc_factor_v, lbl_fs=10, val_fs=11, row_h=34)

    def _on_uc_cat_change(self):
        cat = self._uc_cat.get()
        units = list(self._UNITS.get(cat, {}).keys())
        if not units: return
        self._uc_from_menu.configure(values=units)
        self._uc_to_menu.configure(values=units)
        self._uc_from.set(units[0])
        self._uc_to.set(units[1] if len(units) > 1 else units[0])

    def _calc_units(self):
        try:
            cat = self._uc_cat.get()
            from_u = self._uc_from.get()
            to_u   = self._uc_to.get()
            val    = float(self._uc_val.get())
            units  = self._UNITS.get(cat, {})

            if cat == "Temperature":
                # Special case
                if from_u == to_u:
                    result = val
                elif from_u == "Celsius":
                    result = val * 9/5 + 32 if to_u == "Fahrenheit" else val + 273.15
                elif from_u == "Fahrenheit":
                    result = (val - 32) * 5/9 if to_u == "Celsius" else (val - 32) * 5/9 + 273.15
                else:  # Kelvin
                    result = val - 273.15 if to_u == "Celsius" else (val - 273.15) * 9/5 + 32
                self._uc_result_v.set(f"{result:.6g} {to_u}")
                self._uc_factor_v.set("(Temperature — formula conversion)")
            else:
                from_si = units.get(from_u, 1)
                to_si   = units.get(to_u, 1)
                result  = val * from_si / to_si
                factor  = from_si / to_si
                self._uc_result_v.set(f"{result:,.8g} {to_u}")
                self._uc_factor_v.set(f"1 {from_u} = {factor:,.8g} {to_u}")
        except Exception as e:
            self._uc_result_v.set(f"Error: {e}")

    def _clear_units(self):
        self._uc_val.set('')
        self._uc_result_v.set('—'); self._uc_factor_v.set('—')

    def _sample_units(self):
        self._uc_cat.set('Length'); self._uc_from.set('Foot')
        self._uc_to.set('Meter'); self._uc_val.set('6')

    # ── CURRENCY CONVERTER ──────────────────────────────────────────────────
    _CUR_FLAGS = {
        "USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","JPY":"🇯🇵","CAD":"🇨🇦",
        "AUD":"🇦🇺","CHF":"🇨🇭","CNY":"🇨🇳","INR":"🇮🇳","MXN":"🇲🇽",
        "BRL":"🇧🇷","KRW":"🇰🇷","SGD":"🇸🇬","NOK":"🇳🇴","SEK":"🇸🇪",
        "DKK":"🇩🇰","NZD":"🇳🇿","HKD":"🇭🇰","ZAR":"🇿🇦","AED":"🇦🇪",
        "TTD":"🇹🇹","THB":"🇹🇭","PHP":"🇵🇭","IDR":"🇮🇩","TRY":"🇹🇷",
        "SAR":"🇸🇦","QAR":"🇶🇦","COP":"🇨🇴","PKR":"🇵🇰","EGP":"🇪🇬",
    }

    def _build_currency(self):
        tab = self._all_frames["Currency"]
        ctk.CTkLabel(tab, text="Currency Converter",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab,
                 text="Enter the current exchange rate (from Google, XE.com, or your bank).",
                 font=("Segoe UI",9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))

        # ── Two-column: inputs left, flag panel right ─────────────────────
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill='x', padx=20, pady=(0,8))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # LEFT — inputs
        inner = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        inner.grid(row=0, column=0, sticky="nsew", padx=(0,10))

        currencies = sorted(self._CUR_FLAGS.keys())
        self._cur_amount = labeled_entry(inner,'Amount','1000', on_enter=self._calc_currency)
        # From Currency — ComboBox allows typing any code not in the list
        _fr = ctk.CTkFrame(inner, fg_color='transparent'); _fr.pack(fill='x', pady=3)
        ctk.CTkLabel(_fr, text='From Currency', font=ctk.CTkFont('Segoe UI',10),
                     text_color=TEXT, width=220, anchor='w').pack(side='left')
        self._cur_from = tk.StringVar(value='USD')
        ctk.CTkComboBox(_fr, variable=self._cur_from, values=currencies,
                        fg_color=INPUT_BG, border_color='#B8CCE4',
                        button_color=ACCENT, button_hover_color=NAV_ACT,
                        dropdown_text_color=TEXT,
                        font=ctk.CTkFont('Segoe UI',10), width=200).pack(side='left', padx=8)
        # To Currency — ComboBox allows typing any code not in the list
        _tr = ctk.CTkFrame(inner, fg_color='transparent'); _tr.pack(fill='x', pady=3)
        ctk.CTkLabel(_tr, text='To Currency', font=ctk.CTkFont('Segoe UI',10),
                     text_color=TEXT, width=220, anchor='w').pack(side='left')
        self._cur_to = tk.StringVar(value='EUR')
        ctk.CTkComboBox(_tr, variable=self._cur_to, values=currencies,
                        fg_color=INPUT_BG, border_color='#B8CCE4',
                        button_color=ACCENT, button_hover_color=NAV_ACT,
                        dropdown_text_color=TEXT,
                        font=ctk.CTkFont('Segoe UI',10), width=200).pack(side='left', padx=8)
        tk.Label(inner, text='💡 Tip: type any 3-letter currency code (e.g. TTD, KWD) if not listed — then click Get Current Rates.',
                 font=('Segoe UI', 8), fg=MUTED, bg=CARD, anchor='w'
                 ).pack(anchor='w', padx=8, pady=(0, 4))

        # Exchange rate row with inline button
        _rate_row = ctk.CTkFrame(inner, fg_color="transparent"); _rate_row.pack(fill="x", pady=3)
        ctk.CTkLabel(_rate_row, text='Exchange Rate (1 From = ? To)',
                     font=ctk.CTkFont("Segoe UI",10), text_color=TEXT,
                     width=220, anchor="w").pack(side="left")
        self._cur_rate = tk.StringVar(value='0.92')
        ctk.CTkEntry(_rate_row, textvariable=self._cur_rate, width=110,
                     fg_color=INPUT_BG, border_color=INPUT_BORDER,
                     font=ctk.CTkFont("Segoe UI",10)).pack(side="left", padx=(8,6))
        self._cur_rate_status = tk.StringVar(value='')
        ctk.CTkLabel(_rate_row, textvariable=self._cur_rate_status,
                     font=ctk.CTkFont("Segoe UI",8,slant="italic"),
                     text_color='#276749', anchor='w').pack(side="left", padx=(0,6))
        ctk.CTkButton(_rate_row, text="🌐  Get Current Rates", command=self._fetch_currency_rates,
                      fg_color=NAV_ACT, hover_color=NAV_HOV, text_color='white',
                      font=ctk.CTkFont("Segoe UI",9,"bold"),
                      width=165, height=28, corner_radius=6).pack(side="left")

        # RIGHT — flag panel
        flag_card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        flag_card.grid(row=0, column=1, sticky="nsew")
        flag_card.columnconfigure(0, weight=1)
        flag_card.rowconfigure(0, weight=1)

        flag_inner = ctk.CTkFrame(flag_card, fg_color="transparent")
        flag_inner.place(relx=0.5, rely=0.5, anchor="center")

        self._cur_flag_from_lbl = tk.Label(flag_inner, text="🇺🇸",
                                           font=("Segoe UI",42), bg=CARD)
        self._cur_flag_from_lbl.grid(row=0, column=0, padx=(8,4))
        tk.Label(flag_inner, text="→", font=("Segoe UI",28,"bold"),
                 fg=ACCENT, bg=CARD).grid(row=0, column=1, padx=4)
        self._cur_flag_to_lbl = tk.Label(flag_inner, text="🇪🇺",
                                         font=("Segoe UI",42), bg=CARD)
        self._cur_flag_to_lbl.grid(row=0, column=2, padx=(4,8))

        self._cur_code_from_lbl = tk.Label(flag_inner, text="USD",
                                            font=("Segoe UI",13,"bold"),
                                            fg=TEXT, bg=CARD)
        self._cur_code_from_lbl.grid(row=1, column=0, pady=(2,8))
        tk.Label(flag_inner, text="", bg=CARD).grid(row=1, column=1)
        self._cur_code_to_lbl = tk.Label(flag_inner, text="EUR",
                                          font=("Segoe UI",13,"bold"),
                                          fg=TEXT, bg=CARD)
        self._cur_code_to_lbl.grid(row=1, column=2, pady=(2,8))

        # Update flags when dropdowns change
        def _upd_flags(*_):
            f = self._cur_from.get(); t = self._cur_to.get()
            self._cur_flag_from_lbl.config(text=self._CUR_FLAGS.get(f,'🏳'))
            self._cur_flag_to_lbl.config(text=self._CUR_FLAGS.get(t,'🏳'))
            self._cur_code_from_lbl.config(text=f)
            self._cur_code_to_lbl.config(text=t)
        self._cur_from.trace_add('write', _upd_flags)
        self._cur_to.trace_add('write', _upd_flags)

        calc_button(tab,'Convert →',self._calc_currency,
                    clear_cmd=self._clear_currency, sample_cmd=self._sample_currency)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._cur_result_v  = tk.StringVar(value='—')
        self._cur_reverse_v = tk.StringVar(value='—')
        result_row(res,'Converted Amount',   self._cur_result_v,  color=ACCENT, lbl_fs=10, val_fs=11, row_h=38)
        result_row(res,'Reverse Rate',       self._cur_reverse_v, lbl_fs=10, val_fs=11, row_h=34)
        note = ctk.CTkFrame(tab, fg_color=RES_BG, corner_radius=8)
        note.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(note,
                     text="ℹ️  Exchange rates change constantly. Always verify with a live source before financial decisions.\n"
                          "    Useful sources:  XE.com  |  Google ('USD to EUR')  |  Your bank's FX desk.\n"
                          "    💡 You can type any currency code manually — click Get Current Rates and the app will look it up.",
                     font=ctk.CTkFont("Segoe UI",10), text_color=TEXT, justify='left', anchor='w', wraplength=700
                     ).pack(anchor='w', padx=14, pady=10)

    def _calc_currency(self):
        try:
            amount = float(self._cur_amount.get().replace(',',''))
            rate   = float(self._cur_rate.get())
            result = amount * rate
            self._cur_result_v.set(f"{self._cur_to.get()} {result:,.2f}")
            self._cur_reverse_v.set(f"1 {self._cur_to.get()} = {1/rate:.6g} {self._cur_from.get()}" if rate else '—')
        except Exception as e:
            self._cur_result_v.set(f"Error: {e}")

    def _fetch_currency_rates(self):
        import threading
        self._cur_rate_status.set('fetching…')
        def _do():
            try:
                import urllib.request, json
                from_cur = self._cur_from.get().strip().lower()
                to_cur   = self._cur_to.get().strip().lower()
                if not from_cur or not to_cur:
                    self._cur_rate_status.set('Enter currency codes first')
                    return
                url = f'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{from_cur}.json'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode())
                except Exception as e:
                    if '404' in str(e) or 'HTTP Error 404' in str(e):
                        self._cur_rate_status.set(f'Cannot find currency: {from_cur.upper()}')
                    else:
                        self._cur_rate_status.set('Error — check connection')
                    return
                date_str = data.get('date', '')
                # Reformat YYYY-MM-DD → MM-DD-YYYY
                try:
                    y,m,d = date_str.split('-')
                    date_str = f"{m}-{d}-{y}"
                except Exception: pass
                rates = data.get(from_cur, {})
                if to_cur == from_cur:
                    self._cur_rate.set('1')
                    self._cur_rate_status.set(f'As of {date_str}')
                elif to_cur in rates:
                    self._cur_rate.set(f"{rates[to_cur]:.6g}")
                    self._cur_rate_status.set(f'As of {date_str}')
                else:
                    self._cur_rate_status.set(f'Cannot find currency: {to_cur.upper()}')
            except Exception:
                self._cur_rate_status.set('Error — check connection')
        threading.Thread(target=_do, daemon=True).start()

    def _clear_currency(self):
        self._cur_amount.set(''); self._cur_rate.set('')
        self._cur_result_v.set('—'); self._cur_reverse_v.set('—')

    def _sample_currency(self):
        self._cur_amount.set('1000'); self._cur_from.set('USD')
        self._cur_to.set('EUR'); self._cur_rate.set('0.92')

    # ── TIME & DATE ──────────────────────────────────────────────────────────
    def _build_timedate(self):
        from datetime import date as _d
        tab = self._all_frames["Time & Date"]
        ctk.CTkLabel(tab, text="Time & Date Calculator",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Dates use MM-DD-YYYY format  —  or click 📅 to pick from a calendar",
                 font=("Segoe UI",9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        today_str = _d.today().strftime('%m-%d-%Y')

        def date_row(parent, label, default):
            """Build a date entry row with a calendar button on the right."""
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont("Segoe UI",10),
                         text_color=TEXT, width=220, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            ctk.CTkEntry(row, textvariable=var, width=120,
                         fg_color=INPUT_BG, border_color=INPUT_BORDER,
                         font=ctk.CTkFont("Segoe UI",10)).pack(side="left", padx=(8,4))
            ctk.CTkButton(row, text="📅", command=lambda v=var: self._cal_popup(v),
                          width=32, height=28, fg_color=NAV_ACT, hover_color=NAV_HOV,
                          text_color="white", font=ctk.CTkFont("Segoe UI",11),
                          corner_radius=6).pack(side="left")
            return var

        # Section 1: Date Difference
        s1 = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        s1.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(s1, text="Date Difference",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                     ).pack(anchor='w', padx=14, pady=(8,2))
        self._td_d1 = date_row(s1, 'Start Date  (MM-DD-YYYY)', today_str)
        self._td_d2 = date_row(s1, 'End Date    (MM-DD-YYYY)', today_str)
        # Section 2: Add/Subtract Date
        s2 = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        s2.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(s2, text="Add / Subtract from a Date",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                     ).pack(anchor='w', padx=14, pady=(8,2))
        self._td_base  = date_row(s2, 'Base Date (MM-DD-YYYY)', today_str)
        self._td_delta = labeled_entry(s2,'Days to Add (negative to subtract)','30', on_enter=self._calc_timedate)
        calc_button(tab,'Calculate →',self._calc_timedate,
                    clear_cmd=self._clear_timedate, sample_cmd=self._sample_timedate)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._td_days_v   = tk.StringVar(value='—')
        self._td_weeks_v  = tk.StringVar(value='—')
        self._td_months_v = tk.StringVar(value='—')
        self._td_years_v  = tk.StringVar(value='—')
        self._td_dow_v    = tk.StringVar(value='—')
        self._td_add_v    = tk.StringVar(value='—')
        result_row(res,'Days Between Dates',   self._td_days_v,  color=ACCENT, lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Weeks',                self._td_weeks_v, lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Approx Months',        self._td_months_v,lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Approx Years',         self._td_years_v, lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'End Date Day of Week', self._td_dow_v,   lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Base + Delta =',       self._td_add_v,   lbl_fs=10, val_fs=11, row_h=34)

    def _parse_date(self, s):
        """Parse MM-DD-YYYY string to date object."""
        from datetime import datetime as _dt
        return _dt.strptime(s.strip(), '%m-%d-%Y').date()

    def _cal_popup(self, var):
        """Open a small calendar popup; sets var to MM-DD-YYYY on pick."""
        import calendar as _cal
        from datetime import date as _d
        try: cur = self._parse_date(var.get())
        except: cur = _d.today()

        top = tk.Toplevel(self.winfo_toplevel())
        top.title("Select Date"); top.resizable(False, False)
        top.configure(bg=CARD); top.grab_set()
        # Center over app window
        top.update_idletasks()
        root = self.winfo_toplevel()
        px = root.winfo_x() + root.winfo_width()//2 - 130
        py = root.winfo_y() + root.winfo_height()//2 - 120
        top.geometry(f"260x230+{px}+{py}")

        state = {'y': cur.year, 'm': cur.month}

        # Header bar
        hdr = tk.Frame(top, bg=NAV_BG); hdr.pack(fill='x')
        month_lbl = tk.Label(hdr, text='', bg=NAV_BG, fg='white',
                             font=('Segoe UI',11,'bold'))
        month_lbl.pack(side='left', expand=True, pady=6)
        tk.Button(hdr, text='◀', bg=NAV_BG, fg='white', bd=0, relief='flat',
                  font=('Segoe UI',12,'bold'), activebackground=NAV_ACT,
                  command=lambda: _nav(-1)).pack(side='left', padx=10)
        tk.Button(hdr, text='▶', bg=NAV_BG, fg='white', bd=0, relief='flat',
                  font=('Segoe UI',12,'bold'), activebackground=NAV_ACT,
                  command=lambda: _nav(1)).pack(side='right', padx=10)

        body = tk.Frame(top, bg=CARD); body.pack(fill='both', expand=True, padx=10, pady=6)

        def _nav(delta):
            m = state['m'] + delta; y = state['y']
            if m > 12: m=1; y+=1
            elif m < 1: m=12; y-=1
            state['m']=m; state['y']=y; _build()

        def _build():
            for w in body.winfo_children(): w.destroy()
            month_lbl.config(text=f"{_cal.month_name[state['m']]}  {state['y']}")
            # Day-of-week headers (Sun first)
            for c, d in enumerate(['Su','Mo','Tu','We','Th','Fr','Sa']):
                tk.Label(body, text=d, bg=CARD, fg=MUTED,
                         font=('Segoe UI',8,'bold'), width=3).grid(row=0, column=c)
            first_wd = (_cal.monthrange(state['y'], state['m'])[0] + 1) % 7  # Sun=0
            days_in  = _cal.monthrange(state['y'], state['m'])[1]
            today    = _d.today()
            for day in range(1, days_in+1):
                slot = first_wd + day - 1
                r = slot//7 + 1; c = slot%7
                is_today = (state['y']==today.year and state['m']==today.month and day==today.day)
                bg = ACCENT if is_today else CARD
                fg = 'white' if is_today else TEXT
                def _pick(d=day, y=state['y'], m=state['m']):
                    var.set(f"{m:02d}-{d:02d}-{y}"); top.destroy()
                tk.Button(body, text=str(day), bg=bg, fg=fg, bd=0, relief='flat',
                          font=('Segoe UI',9), width=3, cursor='hand2',
                          activebackground=RES_BG, activeforeground=TEXT,
                          command=_pick).grid(row=r, column=c, pady=1)

        _build()

    def _calc_timedate(self):
        try:
            from datetime import timedelta as _td
            DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            d1 = self._parse_date(self._td_d1.get())
            d2 = self._parse_date(self._td_d2.get())
            diff = (d2 - d1).days
            self._td_days_v.set(f"{diff:,} days")
            self._td_weeks_v.set(f"{diff/7:.2f} weeks  ({diff//7}w {diff%7}d)")
            self._td_months_v.set(f"{diff/30.4375:.2f} months")
            self._td_years_v.set(f"{diff/365.25:.3f} years")
            self._td_dow_v.set(DAYS[d2.weekday()])
            base  = self._parse_date(self._td_base.get())
            delta = int(self._td_delta.get())
            result_date = base + _td(days=delta)
            self._td_add_v.set(f"{result_date.strftime('%m-%d-%Y')}  ({DAYS[result_date.weekday()]})")
        except Exception as e:
            self._td_days_v.set(f"Error: {e}")

    def _clear_timedate(self):
        from datetime import date as _d
        today = _d.today().strftime('%m-%d-%Y')
        self._td_d1.set(today); self._td_d2.set(today)
        self._td_base.set(today); self._td_delta.set('0')
        for v in [self._td_days_v,self._td_weeks_v,self._td_months_v,
                  self._td_years_v,self._td_dow_v,self._td_add_v]: v.set('—')

    def _sample_timedate(self):
        self._td_d1.set('01-01-2024'); self._td_d2.set('12-31-2024')
        self._td_base.set('06-15-2024'); self._td_delta.set('90')


# ═══════════════════════════════════════════════════════════════════════════════
# MEDICAL TAB
# ═══════════════════════════════════════════════════════════════════════════════
class MedicalCalcTab(CalcTabMixin, ctk.CTkFrame):

    ALL_CALCS = ["BMI Calculator", "Body Surface Area", "Drug Dosage",
                 "IV Drip Rate", "Pharmacy Dilution", "Opioid Conversion",
                 "Creatinine Clearance"]

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}
        self._active_calc = self.ALL_CALCS[0]
        self._build()

    def _calculate(self):
        fn = {"BMI Calculator":    self._calc_bmi,
              "Body Surface Area": self._calc_bsa,
              "Drug Dosage":       self._calc_dosage,
              "IV Drip Rate":      self._calc_iv,
              "Pharmacy Dilution": self._calc_dilution,
              "Opioid Conversion": self._calc_opioid,
              "Creatinine Clearance": self._calc_crcl,
              }.get(self._active_calc)
        if fn: fn()

    def show_calculator(self, name):
        for f in self._all_frames.values(): f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    def _build(self):
        for name in self.ALL_CALCS:
            self._all_frames[name] = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._build_bmi(); self._build_bsa(); self._build_dosage()
        self._build_iv(); self._build_dilution(); self._build_opioid()
        self._build_crcl()
        self.show_calculator(self.ALL_CALCS[0])

    # ── BMI ─────────────────────────────────────────────────────────────────
    def _build_bmi(self):
        tab = self._all_frames["BMI Calculator"]
        ctk.CTkLabel(tab, text="BMI Calculator",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Body Mass Index — overwrite the sample data",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._bmi_units   = labeled_option(inner,'Units',
                                           ['Imperial (lbs / in)','Metric (kg / cm)'],
                                           default='Imperial (lbs / in)',
                                           command=lambda v: self._on_bmi_units(v))
        self._bmi_wt_lbl = tk.StringVar(value='Weight (lbs)')
        self._bmi_weight  = labeled_entry_var(inner, self._bmi_wt_lbl, '160', on_enter=self._calc_bmi)
        # Weight conversion hint
        self._bmi_wt_cv = tk.StringVar(value='= 72.6 kg')
        _wr = ctk.CTkFrame(inner, fg_color='transparent'); _wr.pack(fill='x', pady=(0,4))
        ctk.CTkLabel(_wr, text='', width=232, anchor='w', fg_color='transparent').pack(side='left')
        ctk.CTkLabel(_wr, textvariable=self._bmi_wt_cv,
                     font=ctk.CTkFont("Segoe UI",13,slant="italic"), text_color='#276749', anchor='w').pack(side='left')
        self._bmi_ht_lbl = tk.StringVar(value="Height (in)  — e.g. 70 for 5'10\"")
        self._bmi_height  = labeled_entry_var(inner, self._bmi_ht_lbl, '70',
                                          on_enter=self._calc_bmi)
        # Height conversion hint
        self._bmi_ht_cv = tk.StringVar(value="= 5' 10\"  (177.8 cm)")
        _hr = ctk.CTkFrame(inner, fg_color='transparent'); _hr.pack(fill='x', pady=(0,4))
        ctk.CTkLabel(_hr, text='', width=232, anchor='w', fg_color='transparent').pack(side='left')
        ctk.CTkLabel(_hr, textvariable=self._bmi_ht_cv,
                     font=ctk.CTkFont("Segoe UI",13,slant="italic"), text_color='#276749', anchor='w').pack(side='left')
        # Live conversion traces (value changes only — units handled by command callback)
        self._bmi_height.trace_add('write', lambda *_: self._upd_bmi_ht())
        self._bmi_weight.trace_add('write', lambda *_: self._upd_bmi_wt())
        calc_button(tab,'Calculate BMI →',self._calc_bmi,
                    clear_cmd=self._clear_bmi, sample_cmd=self._sample_bmi)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._bmi_v  = tk.StringVar(value='—'); self._bmi_cv = tk.StringVar(value='—')
        self._bmi_hv = tk.StringVar(value='—')
        result_row(res,'BMI Value',            self._bmi_v,  color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Category',             self._bmi_cv, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Healthy Weight Range', self._bmi_hv, lbl_fs=12, val_fs=13, row_h=36)
        scale = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        scale.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(scale, text="BMI Reference Scale",
                     font=ctk.CTkFont("Segoe UI",16,"bold"), text_color=TEXT
                     ).pack(anchor='w', padx=14, pady=(8,4))
        for cat, rng, col in [("Underweight","< 18.5","#2196F3"),("Normal Weight","18.5–24.9","#276749"),
                               ("Overweight","25.0–29.9","#FF9800"),("Obese Class I","30.0–34.9","#FF5722"),
                               ("Obese Class II","35.0–39.9","#E91E63"),("Obese Class III","≥ 40.0","#9C27B0")]:
            r = ctk.CTkFrame(scale, fg_color="transparent"); r.pack(fill='x', padx=14, pady=1)
            ctk.CTkFrame(r, width=8, height=16, fg_color=col, corner_radius=2).pack(side='left', padx=(0,8))
            ctk.CTkLabel(r, text=f"{cat}:  BMI {rng}",
                         font=ctk.CTkFont("Segoe UI",14), text_color=TEXT, anchor='w').pack(side='left')
        tk.Label(scale, text="", bg=CARD, height=1).pack()
        tk.Label(tab, text="⚠  For informational purposes only. Consult a healthcare provider for medical advice.",
                 font=("Segoe UI",10,"italic"), fg=MUTED, bg=APP_BG
                 ).pack(anchor='w', padx=20, pady=(0,12))


    def _on_bmi_units(self, choice):
        """Called by CTkOptionMenu command — choice is the newly selected value."""
        imp = 'Imperial' in choice
        if hasattr(self, '_bmi_ht_lbl'):
            self._bmi_ht_lbl.set("Height (in)  — e.g. 70 for 5'10\"" if imp else "Height (cm)")
        if hasattr(self, '_bmi_wt_lbl'):
            self._bmi_wt_lbl.set('Weight (lbs)' if imp else 'Weight (kg)')
        self._upd_bmi_ht(imp); self._upd_bmi_wt(imp)

    def _upd_bmi_ht(self, imperial=None):
        if imperial is None: imperial = 'Imperial' in self._bmi_units.get()
        try:
            v=float(self._bmi_height.get())
            if imperial:
                ft=int(v)//12; ins=v%12; cm=v*2.54
                self._bmi_ht_cv.set(f"= {ft}\' {ins:.1f}\"  |  {cm:.1f} cm")
            else:
                total_in=v/2.54; ft=int(total_in)//12; ins=total_in%12
                self._bmi_ht_cv.set(f"= {ft}\' {ins:.1f}\"  |  {total_in:.1f} inches")
        except: self._bmi_ht_cv.set('')

    def _upd_bmi_wt(self, imperial=None):
        if imperial is None: imperial = 'Imperial' in self._bmi_units.get()
        try:
            v=float(self._bmi_weight.get())
            if imperial:
                self._bmi_wt_cv.set(f'= {v*0.453592:.1f} kg')
            else:
                self._bmi_wt_cv.set(f'= {v/0.453592:.1f} lbs')
        except: self._bmi_wt_cv.set('')

    def _calc_bmi(self):
        try:
            imperial = 'Imperial' in self._bmi_units.get()
            w = float(self._bmi_weight.get()); h = float(self._bmi_height.get())
            wkg = w * 0.453592 if imperial else w
            hm  = h * 0.0254   if imperial else h / 100
            if hm <= 0: raise ValueError("Height must be > 0")
            bmi = wkg / (hm * hm)
            if bmi < 18.5:   cat = "Underweight"
            elif bmi < 25.0: cat = "Normal Weight ✓"
            elif bmi < 30.0: cat = "Overweight"
            elif bmi < 35.0: cat = "Obese (Class I)"
            elif bmi < 40.0: cat = "Obese (Class II)"
            else:            cat = "Obese (Class III)"
            lo = 18.5 * hm * hm; hi = 24.9 * hm * hm
            if imperial:
                hwt = f"{lo/0.453592:.1f}–{hi/0.453592:.1f} lbs"
            else:
                hwt = f"{lo:.1f}–{hi:.1f} kg"
            self._bmi_v.set(f"{bmi:.1f}"); self._bmi_cv.set(cat); self._bmi_hv.set(hwt)
        except Exception as e:
            self._bmi_v.set(f"Error: {e}")

    def _clear_bmi(self):
        self._bmi_weight.set(''); self._bmi_height.set('')
        for v in [self._bmi_v,self._bmi_cv,self._bmi_hv]: v.set('—')
        self._bmi_ht_cv.set(''); self._bmi_wt_cv.set('')

    def _sample_bmi(self):
        self._bmi_units.set('Imperial (lbs / in)')
        self._bmi_weight.set('160'); self._bmi_height.set('70')

    # ── BODY SURFACE AREA ────────────────────────────────────────────────────
    def _build_bsa(self):
        tab = self._all_frames["Body Surface Area"]
        ctk.CTkLabel(tab, text="Body Surface Area (BSA)",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Used for chemotherapy and critical care drug dosing — overwrite sample data",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._bsa_units = labeled_option(inner,'Units',
                                         ['Imperial (lbs / in)','Metric (kg / cm)'],
                                         default='Imperial (lbs / in)',
                                         command=lambda v: self._on_bsa_units(v))
        self._bsa_ht_lbl = tk.StringVar(value='Height (in)')
        self._bsa_ht = labeled_entry_var(inner, self._bsa_ht_lbl, '70', on_enter=self._calc_bsa)
        self._bsa_ht_cv = tk.StringVar(value="= 5' 10\"  (177.8 cm)")
        _hr = ctk.CTkFrame(inner, fg_color='transparent'); _hr.pack(fill='x', pady=(0,4))
        ctk.CTkLabel(_hr, text='', width=232, anchor='w', fg_color='transparent').pack(side='left')
        ctk.CTkLabel(_hr, textvariable=self._bsa_ht_cv,
                     font=ctk.CTkFont("Segoe UI",13,slant="italic"), text_color='#276749', anchor='w').pack(side='left')
        self._bsa_wt_lbl = tk.StringVar(value='Weight (lbs)')
        self._bsa_wt = labeled_entry_var(inner, self._bsa_wt_lbl, '160',  on_enter=self._calc_bsa)
        self._bsa_wt_cv = tk.StringVar(value='= 72.6 kg')
        _wr = ctk.CTkFrame(inner, fg_color='transparent'); _wr.pack(fill='x', pady=(0,4))
        ctk.CTkLabel(_wr, text='', width=232, anchor='w', fg_color='transparent').pack(side='left')
        ctk.CTkLabel(_wr, textvariable=self._bsa_wt_cv,
                     font=ctk.CTkFont("Segoe UI",13,slant="italic"), text_color='#276749', anchor='w').pack(side='left')
        # Live conversion traces (units change handled by command callback)
        self._bsa_ht.trace_add('write', lambda *_: self._upd_bsa_ht())
        self._bsa_wt.trace_add('write', lambda *_: self._upd_bsa_wt())
        calc_button(tab,'Calculate BSA →',self._calc_bsa,
                    clear_cmd=self._clear_bsa, sample_cmd=self._sample_bsa)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._bsa_most_v = tk.StringVar(value='—'); self._bsa_bois_v = tk.StringVar(value='—')
        self._bsa_avg_v  = tk.StringVar(value='—')
        result_row(res,'Mosteller Formula (√(H×W/3600))', self._bsa_most_v, color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,"Du Bois Formula (0.007184×H⁰·⁷²⁵×W⁰·⁴²⁵)", self._bsa_bois_v, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Average BSA',   self._bsa_avg_v,  lbl_fs=12, val_fs=13, row_h=36)
        info = ctk.CTkFrame(tab, fg_color=RES_BG, corner_radius=8)
        info.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(info, text="📌  Normal Adult BSA: ~1.7 m²  |  Used in oncology dosing: dose (mg) = BSA × dose per m²\n"
                          "⚠  Always verify BSA-based dosing with a pharmacist or oncologist.",
                     font=ctk.CTkFont("Segoe UI",14), text_color=TEXT, justify='left', anchor='w', wraplength=700
                     ).pack(anchor='w', padx=14, pady=10)

    def _on_bsa_units(self, choice):
        """Called by CTkOptionMenu command — choice is the newly selected value."""
        imp = 'Imperial' in choice
        if hasattr(self, '_bsa_ht_lbl'):
            self._bsa_ht_lbl.set('Height (in)' if imp else 'Height (cm)')
        if hasattr(self, '_bsa_wt_lbl'):
            self._bsa_wt_lbl.set('Weight (lbs)' if imp else 'Weight (kg)')
        self._upd_bsa_ht(imp); self._upd_bsa_wt(imp)

    def _upd_bsa_ht(self, imperial=None):
        if imperial is None: imperial = 'Imperial' in self._bsa_units.get()
        try:
            v=float(self._bsa_ht.get())
            if imperial:
                cm=v*2.54; ft=int(v)//12; ins=v%12
                self._bsa_ht_cv.set(f"= {ft}' {ins:.1f}\"  ({cm:.1f} cm)")
            else:
                total_in=v/2.54; ft=int(total_in)//12; ins=total_in%12
                self._bsa_ht_cv.set(f"= {ft}' {ins:.1f}\"  ({total_in:.1f} in)")
        except: self._bsa_ht_cv.set('')

    def _upd_bsa_wt(self, imperial=None):
        if imperial is None: imperial = 'Imperial' in self._bsa_units.get()
        try:
            v=float(self._bsa_wt.get())
            if imperial:
                self._bsa_wt_cv.set(f'= {v*0.453592:.1f} kg')
            else:
                self._bsa_wt_cv.set(f'= {v/0.453592:.1f} lbs  ({v*2.20462:.1f} lb)')
        except: self._bsa_wt_cv.set('')

    def _calc_bsa(self):
        try:
            import math as _m
            imperial = 'Imperial' in self._bsa_units.get()
            ht_raw=float(self._bsa_ht.get()); wt_raw=float(self._bsa_wt.get())
            ht = ht_raw*2.54    if imperial else ht_raw   # to cm
            wt = wt_raw*0.453592 if imperial else wt_raw  # to kg
            mosteller = _m.sqrt(ht * wt / 3600)
            dubois    = 0.007184 * (ht ** 0.725) * (wt ** 0.425)
            avg       = (mosteller + dubois) / 2
            self._bsa_most_v.set(f"{mosteller:.4f} m²"); self._bsa_bois_v.set(f"{dubois:.4f} m²")
            self._bsa_avg_v.set(f"{avg:.4f} m²")
        except Exception as e:
            self._bsa_most_v.set(f"Error: {e}")

    def _clear_bsa(self):
        self._bsa_ht.set(''); self._bsa_wt.set('')
        for v in [self._bsa_most_v,self._bsa_bois_v,self._bsa_avg_v]: v.set('—')
        self._bsa_ht_cv.set(''); self._bsa_wt_cv.set('')

    def _sample_bsa(self):
        self._bsa_units.set('Imperial (lbs / in)')
        self._bsa_ht.set('70'); self._bsa_wt.set('160')

    # ── DRUG DOSAGE ──────────────────────────────────────────────────────────
    def _build_dosage(self):
        tab = self._all_frames["Drug Dosage"]
        ctk.CTkLabel(tab, text="Drug Dosage Calculator",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Weight-based dosing — overwrite the sample data",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._dos_wt_units = labeled_option(inner,'Patient Weight Units',['lbs','kg'], default='lbs')
        self._dos_weight   = labeled_entry(inner,'Patient Weight','154', on_enter=self._calc_dosage)
        self._dos_dose     = labeled_entry(inner,'Recommended Dose (mg/kg)','10', on_enter=self._calc_dosage)
        self._dos_max      = labeled_entry(inner,'Max Single Dose (mg)  — leave blank for no limit','500',
                                           on_enter=self._calc_dosage)
        self._dos_freq     = labeled_option(inner,'Frequency',
                                            ['Once daily','Twice daily (BID)','Three times (TID)',
                                             'Four times (QID)','Every 6 hours','Every 8 hours',
                                             'Every 12 hours','As needed (PRN)'], default='Twice daily (BID)')
        calc_button(tab,'Calculate Dose →',self._calc_dosage,
                    clear_cmd=self._clear_dosage, sample_cmd=self._sample_dosage)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._dos_single_v = tk.StringVar(value='—'); self._dos_daily_v = tk.StringVar(value='—')
        self._dos_weekly_v = tk.StringVar(value='—'); self._dos_capped_v= tk.StringVar(value='—')
        result_row(res,'Single Dose',     self._dos_single_v, color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Daily Dose',      self._dos_daily_v,  lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Weekly Dose',     self._dos_weekly_v, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Max Cap Applied', self._dos_capped_v, lbl_fs=12, val_fs=13, row_h=36)
        tk.Label(tab, text="⚠  Always verify with prescribing information and a licensed pharmacist. Not for direct clinical use.",
                 font=("Segoe UI",10,"italic"), fg=MUTED, bg=APP_BG
                 ).pack(anchor='w', padx=20, pady=(0,12))

    def _calc_dosage(self):
        try:
            wt_kg = float(self._dos_weight.get())
            if 'lbs' in self._dos_wt_units.get(): wt_kg *= 0.453592
            dose_per_kg = float(self._dos_dose.get())
            single = wt_kg * dose_per_kg
            freq_map = {'Once daily':1,'Twice daily (BID)':2,'Three times (TID)':3,
                        'Four times (QID)':4,'Every 6 hours':4,'Every 8 hours':3,
                        'Every 12 hours':2,'As needed (PRN)':1}
            freq = freq_map.get(self._dos_freq.get(), 1)
            max_raw = self._dos_max.get().strip()
            cap_applied = '—'
            if max_raw:
                max_dose = float(max_raw)
                if single > max_dose:
                    single = max_dose
                    cap_applied = f"Capped at {max_dose:.1f} mg max"
                else:
                    cap_applied = f"No cap needed (calc={wt_kg*dose_per_kg:.1f} mg)"
            daily  = single * freq
            weekly = daily * 7
            self._dos_single_v.set(f"{single:.1f} mg")
            self._dos_daily_v.set(f"{daily:.1f} mg / day")
            self._dos_weekly_v.set(f"{weekly:.1f} mg / week")
            self._dos_capped_v.set(cap_applied)
        except Exception as e:
            self._dos_single_v.set(f"Error: {e}")

    def _clear_dosage(self):
        self._dos_weight.set(''); self._dos_dose.set(''); self._dos_max.set('')
        for v in [self._dos_single_v,self._dos_daily_v,self._dos_weekly_v,self._dos_capped_v]: v.set('—')

    def _sample_dosage(self):
        self._dos_wt_units.set('kg'); self._dos_weight.set('70')
        self._dos_dose.set('10'); self._dos_max.set('500')
        self._dos_freq.set('Twice daily (BID)')

    # ── IV DRIP RATE ─────────────────────────────────────────────────────────
    def _build_iv(self):
        tab = self._all_frames["IV Drip Rate"]
        ctk.CTkLabel(tab, text="IV Drip Rate Calculator",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Intravenous infusion rate calculator — overwrite sample data",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._iv_vol  = labeled_entry(inner,'Volume to Infuse (mL)','500', on_enter=self._calc_iv)
        self._iv_time = labeled_entry(inner,'Infusion Time (hours)','4',    on_enter=self._calc_iv)
        self._iv_df   = labeled_option(inner,'Drop Factor (drops/mL)',
                                       ['10 (blood sets)','15 (standard)','20 (pediatric)','60 (micro-drip)'],
                                       default='15 (standard)')
        calc_button(tab,'Calculate →',self._calc_iv,
                    clear_cmd=self._clear_iv, sample_cmd=self._sample_iv)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._iv_dpm_v  = tk.StringVar(value='—'); self._iv_mlh_v  = tk.StringVar(value='—')
        self._iv_tot_v  = tk.StringVar(value='—')
        result_row(res,'Drip Rate (drops/min)',   self._iv_dpm_v, color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Flow Rate (mL/hour)',      self._iv_mlh_v, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Total Drops',              self._iv_tot_v, lbl_fs=12, val_fs=13, row_h=36)
        info = ctk.CTkFrame(tab, fg_color=RES_BG, corner_radius=8)
        info.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(info,
                     text="📌  Drop Factor Guide:\n"
                          "  10 drops/mL  — Blood administration sets\n"
                          "  15 drops/mL  — Standard IV sets (most common)\n"
                          "  20 drops/mL  — Pediatric / KVO sets\n"
                          "  60 drops/mL  — Micro-drip / burette sets\n\n"
                          "  Drops/min = Volume(mL) × Drop Factor ÷ Time(min)\n"
                          "⚠  Always verify with the prescriber and pharmacy before administration.",
                     font=ctk.CTkFont("Segoe UI",14), text_color=TEXT, justify='left', anchor='w', wraplength=700
                     ).pack(anchor='w', padx=14, pady=10)

    def _calc_iv(self):
        try:
            vol  = float(self._iv_vol.get())
            hrs  = float(self._iv_time.get())
            df   = int(self._iv_df.get().split()[0])
            mins = hrs * 60
            dpm  = vol * df / mins
            mlh  = vol / hrs
            tot  = vol * df
            self._iv_dpm_v.set(f"{dpm:.1f} drops/min  (round to nearest whole drop)")
            self._iv_mlh_v.set(f"{mlh:.1f} mL/hour")
            self._iv_tot_v.set(f"{tot:,.0f} total drops")
        except Exception as e:
            self._iv_dpm_v.set(f"Error: {e}")

    def _clear_iv(self):
        self._iv_vol.set(''); self._iv_time.set('')
        for v in [self._iv_dpm_v,self._iv_mlh_v,self._iv_tot_v]: v.set('—')

    def _sample_iv(self):
        self._iv_vol.set('500'); self._iv_time.set('4'); self._iv_df.set('15 (standard)')

    # ── PHARMACY DILUTION ────────────────────────────────────────────────────
    def _build_dilution(self):
        tab = self._all_frames["Pharmacy Dilution"]
        ctk.CTkLabel(tab, text="Pharmacy Dilution Calculator",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="C₁V₁ = C₂V₂  and  Alligation calculations — overwrite sample data",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        # Section: C1V1=C2V2
        s1 = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        s1.pack(fill='x', padx=20, pady=(0,8))
        ctk.CTkLabel(s1, text="Simple Dilution  (C₁V₁ = C₂V₂)",
                     font=ctk.CTkFont("Segoe UI",16,"bold"), text_color=TEXT
                     ).pack(anchor='w', padx=14, pady=(8,2))
        self._dil_c1 = labeled_entry(s1,'Stock Concentration C₁ (%)','10', on_enter=self._calc_dilution)
        self._dil_c2 = labeled_entry(s1,'Desired Concentration C₂ (%)','2',  on_enter=self._calc_dilution)
        self._dil_v2 = labeled_entry(s1,'Final Volume V₂ (mL)','100',        on_enter=self._calc_dilution)
        calc_button(tab,'Calculate →',self._calc_dilution,
                    clear_cmd=self._clear_dilution, sample_cmd=self._sample_dilution)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._dil_v1_v  = tk.StringVar(value='—'); self._dil_dil_v = tk.StringVar(value='—')
        self._dil_solv_v= tk.StringVar(value='—'); self._dil_rat_v = tk.StringVar(value='—')
        result_row(res,'Stock Volume Needed (V₁)',  self._dil_v1_v,  color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Solvent (Diluent) to Add',  self._dil_solv_v,lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Dilution Factor',           self._dil_dil_v, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res,'Ratio (e.g. 1:5)',          self._dil_rat_v, lbl_fs=12, val_fs=13, row_h=36)
        info = ctk.CTkFrame(tab, fg_color=RES_BG, corner_radius=8)
        info.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(info,
                     text="📌  Formula:  C₁V₁ = C₂V₂   →   V₁ = (C₂ × V₂) / C₁\n"
                          "   Solvent to add = V₂ − V₁\n"
                          "   Dilution Factor = C₁ / C₂  (e.g. 5 means 5-fold dilution)\n"
                          "⚠  For illustration only — always verify compounding calculations with a licensed pharmacist.",
                     font=ctk.CTkFont("Segoe UI",14), text_color=TEXT, justify='left', anchor='w', wraplength=700
                     ).pack(anchor='w', padx=14, pady=10)

    def _calc_dilution(self):
        try:
            c1 = float(self._dil_c1.get()); c2 = float(self._dil_c2.get())
            v2 = float(self._dil_v2.get())
            if c1 <= 0: raise ValueError("Stock concentration must be > 0")
            if c2 > c1: raise ValueError("Desired conc must be ≤ stock conc")
            v1 = (c2 * v2) / c1
            solv = v2 - v1
            factor = c1 / c2
            # Ratio: simplify v1:solv ≈ 1:X
            ratio_x = solv / v1 if v1 > 0 else float('inf')
            self._dil_v1_v.set(f"{v1:.3f} mL")
            self._dil_solv_v.set(f"{solv:.3f} mL")
            self._dil_dil_v.set(f"{factor:.2f}× dilution")
            self._dil_rat_v.set(f"1 : {ratio_x:.2f}  (stock : diluent)")
        except Exception as e:
            self._dil_v1_v.set(f"Error: {e}")

    def _clear_dilution(self):
        self._dil_c1.set(''); self._dil_c2.set(''); self._dil_v2.set('')
        for v in [self._dil_v1_v,self._dil_solv_v,self._dil_dil_v,self._dil_rat_v]: v.set('—')

    def _sample_dilution(self):
        self._dil_c1.set('10'); self._dil_c2.set('2'); self._dil_v2.set('100')

    # ── OPIOID CONVERSION ────────────────────────────────────────────────────
    # MME (Morphine Milligram Equivalent) conversion factors
    _MME = {
        "Morphine (oral)":          1.0,
        "Morphine (IV/IM/SC)":      3.0,
        "Oxycodone (oral)":         1.5,
        "Hydrocodone (oral)":       1.0,
        "Hydromorphone (oral)":     4.0,
        "Hydromorphone (IV/IM/SC)": 20.0,
        "Codeine (oral)":           0.15,
        "Fentanyl patch (mcg/hr)":  2.4,
        "Fentanyl IV (mcg)":        0.1,
        "Tramadol (oral)":          0.1,
        "Tapentadol (oral)":        0.4,
        "Buprenorphine SL (mg)":    30.0,
        "Methadone (oral)":         4.0,
    }

    def _build_opioid(self):
        tab = self._all_frames["Opioid Conversion"]
        ctk.CTkLabel(tab, text="Opioid Conversion (MME)",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,2))
        tk.Label(tab,
                 text="Converts between opioids using Morphine Milligram Equivalents (MME).\n"
                      "⚠  Clinical tool — verify all conversions with a pharmacist or prescriber.",
                 font=("Segoe UI",11), fg=MUTED, bg=APP_BG, justify="left", anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,10))

        drugs = list(self._MME.keys())
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))

        self._op_from_drug = labeled_option(inner, 'Current Opioid', drugs,
                                            default='Morphine (oral)', fs=12)
        self._op_dose      = labeled_entry(inner, 'Current Dose (mg, or mcg/hr for patch)',
                                           '10', on_enter=self._calc_opioid, fs=12)
        self._op_freq      = labeled_option(inner, 'Doses Per Day',
                                            ['1','2','3','4','6','8','12','24'],
                                            default='4', fs=12)
        self._op_to_drug   = labeled_option(inner, 'Convert To', drugs,
                                            default='Oxycodone (oral)', fs=12)

        calc_button(tab, 'Calculate Conversion →', self._calc_opioid,
                    clear_cmd=self._clear_opioid, sample_cmd=self._sample_opioid)

        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._op_mme_v    = tk.StringVar(value='—')
        self._op_equiv_v  = tk.StringVar(value='—')
        self._op_perdose_v = tk.StringVar(value='—')
        self._op_risk_v   = tk.StringVar(value='—')
        result_row(res, 'Total Daily MME',           self._op_mme_v,    color='#CC3333', lbl_fs=12, val_fs=13, row_h=38)
        result_row(res, 'Equivalent Daily Dose',     self._op_equiv_v,  color=ACCENT,   lbl_fs=12, val_fs=13, row_h=38)
        result_row(res, 'Equivalent Per-Dose',       self._op_perdose_v, lbl_fs=12, val_fs=13, row_h=38)
        result_row(res, 'MME Risk Level',            self._op_risk_v,   lbl_fs=12, val_fs=13, row_h=38)

        # MME reference table
        ref = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        ref.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(ref, text="MME Conversion Factors",
                     font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT
                     ).pack(anchor='w', padx=14, pady=(10,4))
        for drug, factor in self._MME.items():
            row = ctk.CTkFrame(ref, fg_color="transparent"); row.pack(fill='x', padx=14, pady=1)
            ctk.CTkLabel(row, text=drug, font=ctk.CTkFont("Segoe UI",12),
                         text_color=TEXT, width=280, anchor='w').pack(side='left')
            ctk.CTkLabel(row, text=f"× {factor}", font=ctk.CTkFont("Segoe UI",12,"bold"),
                         text_color=ACCENT, anchor='w').pack(side='left')
        tk.Label(ref, text="", bg=CARD, height=1).pack()

    def _calc_opioid(self):
        try:
            from_drug = self._op_from_drug.get()
            dose      = float(self._op_dose.get())
            freq      = int(self._op_freq.get())
            to_drug   = self._op_to_drug.get()
            from_mme  = self._MME[from_drug]
            to_mme    = self._MME[to_drug]
            daily_mme = dose * from_mme * freq
            equiv_daily = daily_mme / to_mme
            equiv_perdose = equiv_daily / freq
            if daily_mme < 50:   risk = "Low  (< 50 MME/day)"
            elif daily_mme < 90: risk = "Moderate  (50–90 MME/day)"
            elif daily_mme < 200:risk = "High  (90–200 MME/day)"
            else:                risk = "⚠ Very High  (≥ 200 MME/day) — clinical review required"
            self._op_mme_v.set(f"{daily_mme:.2f} MME/day")
            self._op_equiv_v.set(f"{equiv_daily:.2f} mg/day  {to_drug}")
            self._op_perdose_v.set(f"{equiv_perdose:.2f} mg  ×{freq}/day")
            self._op_risk_v.set(risk)
        except Exception as e:
            self._op_mme_v.set(f"Error: {e}")

    def _clear_opioid(self):
        self._op_dose.set('')
        for v in [self._op_mme_v, self._op_equiv_v, self._op_perdose_v, self._op_risk_v]:
            v.set('—')

    def _sample_opioid(self):
        self._op_from_drug.set('Hydrocodone (oral)')
        self._op_dose.set('10'); self._op_freq.set('4')
        self._op_to_drug.set('Oxycodone (oral)')


    # -- CREATININE CLEARANCE (Cockcroft-Gault) --------------------------

    def _build_crcl(self):
        tab = self._all_frames["Creatinine Clearance"]
        ctk.CTkLabel(tab, text="Creatinine Clearance  (Cockcroft-Gault)",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(tab,
                 text="Estimates kidney function for drug-dose adjustments.\n"
                      "Formula:  ((140 - age) x weight x 0.85*)  /  (72 x SCr)"
                      "   *females only.\n"
                      "For informational purposes only. "
                      "Verify with a pharmacist or prescriber.",
                 font=("Segoe UI", 11), fg=MUTED, bg=APP_BG,
                 justify="left", anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0, 10))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill="x", padx=20, pady=(0, 8))
        self._crcl_age = labeled_entry(inner, "Age (years)", "65",
                                       on_enter=self._calc_crcl)
        self._crcl_units = labeled_option(inner, 'Units',
                                          ['Imperial (lbs)', 'Metric (kg)'],
                                          default='Imperial (lbs)',
                                          command=lambda v: self._on_crcl_units(v))
        self._crcl_wt_lbl = tk.StringVar(value='Weight (lbs)')
        self._crcl_wt  = labeled_entry_var(inner, self._crcl_wt_lbl, '160',
                                           on_enter=self._calc_crcl)
        self._crcl_wt_cv = tk.StringVar(value='= 72.6 kg')
        _cwr = ctk.CTkFrame(inner, fg_color='transparent')
        _cwr.pack(fill='x', pady=(0, 4))
        ctk.CTkLabel(_cwr, text='', width=232, anchor='w',
                     fg_color='transparent').pack(side='left')
        ctk.CTkLabel(_cwr, textvariable=self._crcl_wt_cv,
                     font=ctk.CTkFont("Segoe UI", 13, slant="italic"),
                     text_color='#276749', anchor='w').pack(side='left')
        self._crcl_wt.trace_add('write', lambda *_: self._upd_crcl_wt())
        self._crcl_sex = labeled_option(inner, "Sex", ["Male", "Female"],
                                        default="Male")
        self._crcl_scr = labeled_entry(inner, "Serum Creatinine (mg/dL)", "1.2",
                                       on_enter=self._calc_crcl)
        calc_button(tab, 'Calculate →', self._calc_crcl,
                    clear_cmd=self._clear_crcl,
                    sample_cmd=self._sample_crcl)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill="x", padx=20, pady=(0, 8))
        self._crcl_v    = tk.StringVar(value="--")
        self._crcl_cat  = tk.StringVar(value="--")
        self._crcl_note = tk.StringVar(value="--")
        result_row(res, "CrCl (mL/min)",   self._crcl_v,
                   color=ACCENT, lbl_fs=12, val_fs=13, row_h=36)
        result_row(res, "CKD Stage",        self._crcl_cat,  color=TEXT)
        result_row(res, "Drug Dosing Note", self._crcl_note, color=TEXT)

    def _on_crcl_units(self, choice):
        imp = 'Imperial' in choice
        if hasattr(self, '_crcl_wt_lbl'):
            self._crcl_wt_lbl.set('Weight (lbs)' if imp else 'Weight (kg)')
        self._upd_crcl_wt(imp)

    def _upd_crcl_wt(self, imperial=None):
        if imperial is None:
            imperial = 'Imperial' in self._crcl_units.get()
        try:
            v = float(self._crcl_wt.get())
            if imperial:
                self._crcl_wt_cv.set(f'= {v * 0.453592:.1f} kg')
            else:
                self._crcl_wt_cv.set(f'= {v / 0.453592:.1f} lbs')
        except:
            self._crcl_wt_cv.set('')

    def _calc_crcl(self):
        try:
            age = float(self._crcl_age.get())
            imperial = 'Imperial' in self._crcl_units.get()
            wt_raw = float(self._crcl_wt.get())
            wt = wt_raw * 0.453592 if imperial else wt_raw
            scr = float(self._crcl_scr.get())
            if age <= 0 or wt <= 0 or scr <= 0:
                self._crcl_v.set("Values must be > 0"); return
            female = (self._crcl_sex.get() == "Female")
            crcl = max(0.0, round(
                ((140 - age) * wt * (0.85 if female else 1.0)) / (72 * scr), 1))
            if   crcl >= 90: cat = "G1 - Normal / High  (>= 90 mL/min)"
            elif crcl >= 60: cat = "G2 - Mildly Decreased  (60-89)"
            elif crcl >= 30: cat = "G3 - Moderately Decreased  (30-59)"
            elif crcl >= 15: cat = "G4 - Severely Decreased  (15-29)"
            else:             cat = "G5 - Kidney Failure  (< 15)"
            if   crcl >= 50: note = "No routine adjustment -- monitor closely"
            elif crcl >= 30: note = "Adjust doses for renally cleared drugs"
            elif crcl >= 15: note = "Significant reduction required -- consult pharmacist"
            else:             note = "Dialysis/supportive care considerations apply"
            self._crcl_v.set(str(crcl) + " mL/min")
            self._crcl_cat.set(cat)
            self._crcl_note.set(note)
        except Exception as e:
            self._crcl_v.set("Error: " + str(e))

    def _clear_crcl(self):
        for v in [self._crcl_age, self._crcl_wt, self._crcl_scr]: v.set("")
        self._crcl_sex.set("Male")
        self._crcl_units.set("Imperial (lbs)")
        self._crcl_wt_lbl.set("Weight (lbs)")
        self._crcl_wt_cv.set("")
        for v in [self._crcl_v, self._crcl_cat, self._crcl_note]: v.set("--")

    def _sample_crcl(self):
        self._crcl_age.set("68")
        self._crcl_wt.set("181")
        self._crcl_sex.set("Male")
        self._crcl_scr.set("1.4")


class ElectronicsCalcTab(CalcTabMixin, ctk.CTkFrame):

    ALL_CALCS = ["Ohm's Law", "Series / Parallel Resistors", "Voltage Divider"]

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG)
        self._all_frames  = {}
        self._active_calc = self.ALL_CALCS[0]
        self._build()

    def _calculate(self):
        fn = {"Ohm's Law":                 self._calc_ohms,
              "Series / Parallel Resistors": self._calc_spr,
              "Voltage Divider":            self._calc_vdiv,
              }.get(self._active_calc)
        if fn: fn()

    def show_calculator(self, name):
        for f in self._all_frames.values(): f.place_forget()
        self._all_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_calc = name

    def _build(self):
        for name in self.ALL_CALCS:
            self._all_frames[name] = ctk.CTkScrollableFrame(self, fg_color=APP_BG)
        self._build_ohms(); self._build_spr(); self._build_vdiv()
        self.show_calculator(self.ALL_CALCS[0])

    # ── HELPER: draw vertical zigzag resistor on canvas ─────────────────────
    def _draw_res_v(self, c, x, y1, y2, col, w=10, n=5):
        m = int((y2-y1)*0.15)
        by1,by2 = y1+m, y2-m; bh=by2-by1
        c.create_line(x,y1, x,by1, fill=col, width=2)
        c.create_line(x,by2, x,y2,  fill=col, width=2)
        step=bh/(n+1); pts=[x,by1]
        for i in range(n):
            pts.extend([x+(w if i%2==0 else -w), by1+(i+1)*step])
        pts.extend([x,by2]); c.create_line(*pts, fill=col, width=2)

    # ── OHM'S LAW ────────────────────────────────────────────────────────────
    def _build_ohms(self):
        tab = self._all_frames["Ohm's Law"]
        ctk.CTkLabel(tab, text="Ohm's Law Calculator",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))

        # ── Two-column body: inputs left, circle right ────────────────────────
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill='x', padx=20, pady=(0,8))
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # ── LEFT: input card ──────────────────────────────────────────────────
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,10))

        ctk.CTkLabel(left, text="Enter any TWO known values — solve the others",
                     font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=14, pady=(12,2))
        tk.Label(left, text="Leave fields blank for unknowns.\nUse scientific notation e.g. 4.7e3 for 4700",
                 font=("Segoe UI",9), fg=MUTED, bg=CARD, justify="left", anchor="w"
                 ).pack(anchor="w", padx=14, pady=(0,10))

        self._ohm_e = labeled_entry(left, 'Voltage  E (Volts)',   '', on_enter=self._calc_ohms)
        self._ohm_i = labeled_entry(left, 'Current  I (Amps)',    '', on_enter=self._calc_ohms)
        self._ohm_r = labeled_entry(left, 'Resistance  R (Ohms)', '', on_enter=self._calc_ohms)
        self._ohm_p = labeled_entry(left, 'Power  P (Watts)',     '', on_enter=self._calc_ohms)

        # Buttons below fields — contained within the left card
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill='x', padx=14, pady=(10,16))
        ctk.CTkButton(btn_row, text="Sample", command=self._sample_ohms,
                      fg_color=INPUT_BG, text_color=ACCENT, hover_color=RES_BG,
                      font=ctk.CTkFont("Segoe UI",10), width=72, height=36,
                      corner_radius=8).pack(side="left", padx=(0,6))
        ctk.CTkButton(btn_row, text="Clear", command=self._clear_ohms,
                      fg_color=BTN_SECONDARY, text_color=TEXT, hover_color=BORDER,
                      font=ctk.CTkFont("Segoe UI",10), width=72, height=36,
                      corner_radius=8).pack(side="left", padx=(0,6))
        ctk.CTkButton(btn_row, text="Calculate →", command=self._calc_ohms,
                      fg_color=ACCENT, hover_color=NAV_ACT,
                      font=ctk.CTkFont("Segoe UI",10,"bold"),
                      height=36, corner_radius=8).pack(side="left")

        # ── RIGHT: circle card ────────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew")

        self._ohm_cv = tk.Canvas(right, height=420, bg=CARD, highlightthickness=0)
        self._ohm_cv.pack(fill='x', padx=6, pady=6)
        self._ohm_cv.bind('<Configure>',
            lambda e: self._draw_ohms_circle(self._ohm_cv, e.width, e.height))
        self._ohm_cv.after(80, lambda:
            self._draw_ohms_circle(self._ohm_cv,
                                   self._ohm_cv.winfo_width() or 460,
                                   self._ohm_cv.winfo_height() or 420))

        # ── Results below both columns ────────────────────────────────────────
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,12))
        self._ohm_ev = tk.StringVar(value='—'); self._ohm_iv = tk.StringVar(value='—')
        self._ohm_rv = tk.StringVar(value='—'); self._ohm_pv = tk.StringVar(value='—')
        result_row(res,'Voltage  E',     self._ohm_ev, color='#4477CC', lbl_fs=10, val_fs=11, row_h=36)
        result_row(res,'Current  I',     self._ohm_iv, color='#CC3333', lbl_fs=10, val_fs=11, row_h=36)
        result_row(res,'Resistance  R',  self._ohm_rv, color='#CCAA22', lbl_fs=10, val_fs=11, row_h=36)
        result_row(res,'Power  P',       self._ohm_pv, color='#33AA33', lbl_fs=10, val_fs=11, row_h=36)

    def _draw_ohms_circle(self, c, W, H):
        import math as _m
        c.delete('all')
        CE='#4477CC'; CI='#CC3333'; CP='#33AA33'; CR='#CCAA22'
        # Reserve top space for title
        title_h = 26
        cx=W//2; cy=title_h + (H-title_h)//2
        R=min(cx, (H-title_h)//2)-8
        Ri=int(R*0.55)   # larger inner circle — gives labels room to breathe
        Rf=int(R*0.77)   # mid-ring radius — visually centers formula in each sector
        # Title above the circle
        c.create_text(cx, 4, text="OHM'S LAW CIRCLE", fill=NAV_BG,
                      font=('Segoe UI', 10, 'bold'), anchor='n')
        # 4 colored quadrant pie slices
        for start, col in [(0,CE),(90,CI),(180,CP),(270,CR)]:
            c.create_arc(cx-R,cy-R,cx+R,cy+R, start=start, extent=90,
                         style='pieslice', fill=col, outline='white', width=2)
        # Sub-dividers (30° and 60° within each quadrant)
        for base in [0,90,180,270]:
            for off in [30,60]:
                a=_m.radians(base+off)
                c.create_line(cx,cy,int(cx+R*_m.cos(a)),int(cy-R*_m.sin(a)),fill='white',width=1)
        # Formula text (3 per quadrant at angles base+15, +45, +75)
        fmls = {
            0:  [("E = R·I",15),("E = P÷I",45),("E=√(P·R)",75)],
            90: [("I = E÷R",15),("I = P÷E",45),("I=√(P÷R)",75)],
            180:[("P = E·I",15),("P = I²R",45),("P = E²÷R",75)],
            270:[("R = E÷I",15),("R = E²÷P",45),("R = P÷I²",75)],
        }
        for base, items in fmls.items():
            for txt, off in items:
                a=_m.radians(base+off)
                c.create_text(int(cx+Rf*_m.cos(a)),int(cy-Rf*_m.sin(a)),
                              text=txt, fill='white',
                              font=('Segoe UI', max(9, int(R*0.057)), 'bold'), anchor='center')
        # Inner white circle
        c.create_oval(cx-Ri,cy-Ri,cx+Ri,cy+Ri, fill='white', outline='#C0C0C0', width=1)
        # Cross dividers inside inner circle
        c.create_line(cx-Ri+4,cy,cx+Ri-4,cy, fill='#D0D0D0', width=1)
        c.create_line(cx,cy-Ri+4,cx,cy+Ri-4, fill='#D0D0D0', width=1)

        # ── Center labels ──────────────────────────────────────────────────────
        # Layout: letter sits close to the center cross; sub-text is pushed into
        # the outer part of each quadrant.  Top quadrants: letter below, sub-text
        # above (anchor='s').  Bottom quadrants: letter above, sub-text below
        # (anchor='n').  This keeps everything within the inner circle.
        o   = int(Ri * 0.46)   # horizontal distance from center to label column
        ltr_off = int(Ri * 0.20)   # letter center distance from center line
        txt_off = int(Ri * 0.38)   # sub-text close to letter, stays well inside circle
        fs  = max(11, int(Ri * 0.24))   # large letter font (unchanged)
        fsm = max( 6, int(Ri * 0.10))   # sub-text font — smaller so it fits cleanly

        labels = [
            # (dx, sign,  letter, sub-text,          color)
            (-o,  -1,    'I',   'Current\n(Amps)',  CI),   # top-left
            ( o,  -1,    'E',   'Voltage\n(Volts)', CE),   # top-right
            (-o,  +1,    'P',   'Power\n(Watts)',   CP),   # bottom-left
            ( o,  +1,    'R',   'Resistance\n(Ohms)',CR),  # bottom-right
        ]
        for (dx, sign, lbl, sub, col) in labels:
            ltr_y = cy + sign * ltr_off   # letter y: close to center line
            txt_y = cy + sign * txt_off   # sub-text y: pushed into quadrant

            c.create_text(cx+dx, ltr_y, text=lbl, fill=col,
                          font=('Segoe UI', fs, 'bold'), anchor='center')
            # sub-text anchor: 'n' for bottom quadrants (text grows downward away from center),
            # 's' for top quadrants (text grows upward away from center)
            anc = 'n' if sign > 0 else 's'
            c.create_text(cx+dx, txt_y, text=sub, fill=col,
                          font=('Segoe UI', fsm), anchor=anc, justify='center')

    def _calc_ohms(self):
        try:
            import math as _m
            def g(v): s=v.get().strip(); return float(s) if s else None
            E=g(self._ohm_e); I=g(self._ohm_i); R=g(self._ohm_r); P=g(self._ohm_p)
            known = sum(x is not None for x in [E,I,R,P])
            if known < 2: raise ValueError("Enter at least 2 values")
            # Solve iteratively (handle all pairs)
            for _ in range(4):
                if E and I: R=R or E/I; P=P or E*I
                if E and R: I=I or E/R; P=P or E*E/R
                if E and P: I=I or P/E; R=R or E*E/P
                if I and R: E=E or I*R; P=P or I*I*R
                if I and P: E=E or P/I; R=R or P/(I*I)
                if R and P: E=E or _m.sqrt(P*R); I=I or _m.sqrt(P/R)
            def fmt(v): return f'{v:.6g}' if v else '—'
            self._ohm_ev.set(f'{fmt(E)} V'); self._ohm_iv.set(f'{fmt(I)} A')
            self._ohm_rv.set(f'{fmt(R)} Ω'); self._ohm_pv.set(f'{fmt(P)} W')
        except Exception as e:
            self._ohm_ev.set(f'Error: {e}')

    def _clear_ohms(self):
        for v in [self._ohm_e,self._ohm_i,self._ohm_r,self._ohm_p]: v.set('')
        for v in [self._ohm_ev,self._ohm_iv,self._ohm_rv,self._ohm_pv]: v.set('—')

    def _sample_ohms(self):
        self._ohm_e.set('12'); self._ohm_r.set('470')
        self._ohm_i.set(''); self._ohm_p.set('')

    # ── SERIES / PARALLEL RESISTORS ──────────────────────────────────────────
    def _build_spr(self):
        tab = self._all_frames["Series / Parallel Resistors"]
        ctk.CTkLabel(tab, text="Series / Parallel Resistors",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab, text="Overwrite the sample data",
                 font=("Segoe UI",9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,8))
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._spr_mode = labeled_option(inner,'Configuration',['Series','Parallel'], default='Series')
        ctk.CTkLabel(inner, text="Enter up to 8 resistors (leave extras blank):",
                     font=ctk.CTkFont("Segoe UI",10), text_color=MUTED
                     ).pack(anchor='w', padx=14, pady=(4,2))
        self._spr_rs = []
        defaults = ['100','220','470','','','','','']
        for i in range(8):
            v = labeled_entry(inner, f'R{i+1} (Ω)', defaults[i], on_enter=self._calc_spr)
            self._spr_rs.append(v)
        calc_button(tab,'Calculate →',self._calc_spr,
                    clear_cmd=self._clear_spr, sample_cmd=self._sample_spr)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._spr_total_v = tk.StringVar(value='—'); self._spr_count_v = tk.StringVar(value='—')
        self._spr_cond_v  = tk.StringVar(value='—')
        result_row(res,'Total Resistance',   self._spr_total_v, color=ACCENT, lbl_fs=10, val_fs=11, row_h=36)
        result_row(res,'Resistors Used',     self._spr_count_v, lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Total Conductance',  self._spr_cond_v,  lbl_fs=10, val_fs=11, row_h=34)
        info = ctk.CTkFrame(tab, fg_color=RES_BG, corner_radius=8)
        info.pack(fill='x', padx=20, pady=(0,12))
        ctk.CTkLabel(info,
                     text="📌  Series:    R_total = R1 + R2 + … + Rn\n"
                          "    Parallel: 1/R_total = 1/R1 + 1/R2 + … + 1/Rn\n"
                          "    Conductance (S) = 1 / R_total",
                     font=ctk.CTkFont("Segoe UI",10), text_color=TEXT,
                     justify='left', anchor='w'
                     ).pack(anchor='w', padx=14, pady=10)

    def _calc_spr(self):
        try:
            vals = []
            for v in self._spr_rs:
                s = v.get().strip()
                if s: vals.append(float(s))
            if not vals: raise ValueError("Enter at least one resistor value")
            mode = self._spr_mode.get()
            if mode == 'Series':
                total = sum(vals)
            else:
                total = 1 / sum(1/r for r in vals)
            cond = 1/total if total else float('inf')
            self._spr_total_v.set(f'{total:.6g} Ω')
            self._spr_count_v.set(str(len(vals)))
            self._spr_cond_v.set(f'{cond:.6g} S (Siemens)')
        except Exception as e:
            self._spr_total_v.set(f'Error: {e}')

    def _clear_spr(self):
        for v in self._spr_rs: v.set('')
        for v in [self._spr_total_v,self._spr_count_v,self._spr_cond_v]: v.set('—')

    def _sample_spr(self):
        defaults=['100','220','470','','','','','']
        for v,d in zip(self._spr_rs,defaults): v.set(d)
        self._spr_mode.set('Series')

    # ── VOLTAGE DIVIDER ───────────────────────────────────────────────────────
    def _build_vdiv(self):
        tab = self._all_frames["Voltage Divider"]
        ctk.CTkLabel(tab, text="Voltage Divider Calculator",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(16,4))
        tk.Label(tab,
                 text="Vout = Vs × R2 / (R1 + R2)   — Enter any three values to solve for the fourth",
                 font=("Segoe UI",9), fg=MUTED, bg=APP_BG, anchor="w"
                 ).pack(anchor="w", padx=20, pady=(0,6))
        # Circuit diagram
        diag_card = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        diag_card.pack(fill='x', padx=20, pady=(0,8))
        self._vdiv_cv = tk.Canvas(diag_card, height=300, bg=CARD, highlightthickness=0)
        self._vdiv_cv.pack(fill='x', padx=10, pady=8)
        self._vdiv_cv.bind('<Configure>',
            lambda e: self._draw_vdiv_circuit(self._vdiv_cv, e.width, 300))
        self._vdiv_cv.after(50, lambda:
            self._draw_vdiv_circuit(self._vdiv_cv, self._vdiv_cv.winfo_width() or 520, 300))
        # Calculator
        inner = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        inner.pack(fill='x', padx=20, pady=(0,8))
        self._vd_vs   = labeled_entry(inner,'Source Voltage  Vs (V)','12',  on_enter=self._calc_vdiv)
        self._vd_r1   = labeled_entry(inner,'Resistor 1  R1 (Ω)',   '1000', on_enter=self._calc_vdiv)
        self._vd_r2   = labeled_entry(inner,'Resistor 2  R2 (Ω)',   '2200', on_enter=self._calc_vdiv)
        self._vd_vout = labeled_entry(inner,'Output Voltage  Vout (V)','', on_enter=self._calc_vdiv)
        calc_button(tab,'Calculate →',self._calc_vdiv,
                    clear_cmd=self._clear_vdiv, sample_cmd=self._sample_vdiv)
        res = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=10)
        res.pack(fill='x', padx=20, pady=(0,8))
        self._vd_vout_v = tk.StringVar(value='—'); self._vd_cur_v  = tk.StringVar(value='—')
        self._vd_p1_v   = tk.StringVar(value='—'); self._vd_p2_v   = tk.StringVar(value='—')
        self._vd_ptot_v = tk.StringVar(value='—')
        result_row(res,'Output Voltage  Vout', self._vd_vout_v, color=ACCENT, lbl_fs=10, val_fs=11, row_h=36)
        result_row(res,'Divider Current  I',   self._vd_cur_v,  lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Power in R1  P1',       self._vd_p1_v,  lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Power in R2  P2',       self._vd_p2_v,  lbl_fs=10, val_fs=11, row_h=34)
        result_row(res,'Total Power Dissipated',self._vd_ptot_v,lbl_fs=10, val_fs=11, row_h=34)

    def _draw_vdiv_circuit(self, c, W, H):
        c.delete('all')
        COL=NAV_BG; RED='#CC3333'; BLU=ACCENT
        L=int(W*0.14); Rx=int(W*0.62); T=int(H*0.10); B=int(H*0.90); mid=(T+B)//2
        jy=int(T+(B-T)*0.58)
        # Wires
        c.create_line(L,T, Rx,T, fill=COL,width=3)
        c.create_line(L,B, Rx,B, fill=COL,width=3)
        c.create_line(L,T, L,mid-24, fill=COL,width=3)
        c.create_line(L,mid+24, L,B, fill=COL,width=3)
        # Battery
        for dy,lw,hw in [(-20,3,18),(-12,2,11),(12,3,18),(20,2,11)]:
            c.create_line(L-hw,mid+dy, L+hw,mid+dy, fill=COL, width=lw)
        c.create_text(L+28,mid-15, text='+', fill=COL, font=('Segoe UI',13,'bold'))
        c.create_text(L+28,mid+12, text='−', fill=COL, font=('Segoe UI',15,'bold'))
        c.create_text(L-12,mid, text='Vs', fill=BLU, font=('Segoe UI',11,'bold'), anchor='e')
        # R1 and R2
        self._draw_res_v(c, Rx, T, jy, COL)
        self._draw_res_v(c, Rx, jy, B, COL)
        c.create_text(Rx+44,(T+jy)//2, text='R₁', fill=BLU, font=('Segoe UI',13,'bold'), anchor='w')
        c.create_text(Rx+44,(jy+B)//2, text='R₂', fill=BLU, font=('Segoe UI',13,'bold'), anchor='w')
        # Output tap
        outx=int(Rx+W*0.10)
        c.create_line(Rx,jy, outx,jy, fill=RED, width=2, dash=(6,3))
        c.create_oval(Rx-5,jy-5,Rx+5,jy+5, fill=RED, outline=RED)
        c.create_text(outx+6,jy, text='Vout', fill=RED, font=('Segoe UI',11,'bold'), anchor='w')
        # Formula
        c.create_text(W//2,8, text='Vout = Vs × R2 / (R1 + R2)',
                      fill=NAV_BG, font=('Segoe UI',10,'bold'), anchor='n')
        c.create_text(int(W*0.82),int(jy+20),
                      text='Output\nVoltage', fill=RED, font=('Segoe UI',8), anchor='n', justify='center')

    def _calc_vdiv(self):
        try:
            def g(v): s=v.get().strip(); return float(s) if s else None
            Vs=g(self._vd_vs); R1=g(self._vd_r1); R2=g(self._vd_r2); Vo=g(self._vd_vout)
            known=sum(x is not None for x in [Vs,R1,R2,Vo])
            if known < 3: raise ValueError("Enter at least 3 values")
            if Vs and R1 and R2:
                Vo = Vs * R2 / (R1 + R2)
            elif Vs and R1 and Vo:
                R2 = Vo * R1 / (Vs - Vo) if Vs != Vo else float('inf')
            elif Vs and R2 and Vo:
                R1 = R2 * (Vs - Vo) / Vo if Vo else float('inf')
            elif R1 and R2 and Vo:
                Vs = Vo * (R1 + R2) / R2
            I    = Vs / (R1 + R2)
            P1   = I * I * R1
            P2   = I * I * R2
            self._vd_vout_v.set(f'{Vo:.6g} V')
            self._vd_cur_v.set(f'{I:.6g} A')
            self._vd_p1_v.set(f'{P1:.6g} W')
            self._vd_p2_v.set(f'{P2:.6g} W')
            self._vd_ptot_v.set(f'{P1+P2:.6g} W')
        except Exception as e:
            self._vd_vout_v.set(f'Error: {e}')

    def _clear_vdiv(self):
        for v in [self._vd_vs,self._vd_r1,self._vd_r2,self._vd_vout]: v.set('')
        for v in [self._vd_vout_v,self._vd_cur_v,self._vd_p1_v,self._vd_p2_v,self._vd_ptot_v]: v.set('—')

    def _sample_vdiv(self):
        self._vd_vs.set('12'); self._vd_r1.set('1000')
        self._vd_r2.set('2200'); self._vd_vout.set('')



class App(ctk.CTk):
    TABS = [
        ("🔢  Basic Calculator",    BasicCalcTab),
        ("🔬  Scientific & Graph",  ScientificGraphingCalcTab),
        ("🏗  Construction",        ConstructionCalcTab),
        ("🔄  Conversion",          ConversionCalcTab),
        ("⚡  Electronics",         ElectronicsCalcTab),
        ("💹  Finance",             FinanceCalcTab),
        ("🌐  IT Networking",       ITNetworkingCalcTab),
        ("🏥  Medical",             MedicalCalcTab),
    ]

    def __init__(self):
        super().__init__()
        self.title("Beeran's Calculator Suite")
        self.geometry("1400x950")
        self.minsize(1100, 700)
        self.update_idletasks()
        sw=self.winfo_screenwidth(); sh=self.winfo_screenheight()
        x=(sw-1400)//2; y=max(0,(sh-950)//2)
        self.geometry(f"1400x950+{x}+{y}")
        self.configure(fg_color=APP_BG)

        self._active_btn = None
        self._active_idx = None
        self._frames     = {}

        self._build_sidebar()
        self._build_content()
        self._font_offset = 0   # tracks cumulative font-size delta
        self._select(0)
        self.after(150, self._apply_startup_settings)
        self.after(200, self._prebuild_tabs)  # background-build remaining tabs
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=NAV_BG)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # ── Settings + About buttons — pack bottom FIRST so expand works correctly ──
        # Pack order (first packed = lowest on screen): separator → About → Settings
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#2F5496").pack(
            fill="x", padx=20, pady=(8, 6), side="bottom")
        ctk.CTkButton(self.sidebar, text="ℹ️   About",
                      fg_color="#16294E", hover_color=NAV_HOV,
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=36, corner_radius=8,
                      command=self._open_about).pack(
                          side="bottom", pady=(0, 4), padx=14, fill="x")
        ctk.CTkButton(self.sidebar, text="⚙   Settings",
                      fg_color=NAV_ACT, hover_color=NAV_HOV,
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=36, corner_radius=8,
                      command=self._open_settings).pack(
                          side="bottom", pady=(0, 4), padx=14, fill="x")
        self.theme_var = tk.StringVar(value="Light")  # kept for _change_theme compatibility

        # ── Logo ─────────────────────────────────────────
        ctk.CTkLabel(self.sidebar, text="⚙️  Beeran's  ⚙️\nCalculator\nSuite",
                     font=ctk.CTkFont("Segoe UI", 16, "bold"),
                     text_color="white", justify="center").pack(pady=(28, 4))
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#2F5496").pack(
            fill="x", padx=20, pady=(8, 12))

        # ── Nav area (main ↔ construction) ────────────────
        self._nav_area = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._nav_area.pack(fill="both", expand=True)

        # Main nav — 5 buttons + separator
        self._main_nav = ctk.CTkFrame(self._nav_area, fg_color="transparent")
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._nav_btns = []
        for i, (label, _) in enumerate(self.TABS):
            if i == 2:  # separator after Basic + Scientific
                self._nav_sep = ctk.CTkFrame(self._main_nav, height=3,
                                             fg_color="#90C8F0")
                self._nav_sep.pack(fill="x", padx=8, pady=(6, 6))
            if "Construction" in label:    cmd = self._enter_construction
            elif "Conversion" in label:    cmd = self._enter_conversion
            elif "Electronics" in label:   cmd = self._enter_electronics
            elif "Finance" in label:       cmd = self._enter_finance
            elif "IT Networking" in label: cmd = self._enter_it
            elif "Medical" in label:       cmd = self._enter_medical
            else:                          cmd = lambda idx=i: self._select(idx)
            btn = ctk.CTkButton(
                self._main_nav, text=label,
                font=ctk.CTkFont("Segoe UI", 14, "bold"),
                fg_color="transparent", hover_color=NAV_HOV,
                text_color="white", anchor="w",
                height=44, corner_radius=8, command=cmd)
            btn.pack(fill="x", padx=12, pady=2)
            self._nav_btns.append(btn)

        # ── helper: build a drill-down nav panel ───────────────────────────
        def _make_nav(title, back_cmd, items, select_cmd):
            nav = ctk.CTkFrame(self._nav_area, fg_color="transparent")
            ctk.CTkLabel(nav, text=title,
                         font=ctk.CTkFont("Segoe UI", 14, "bold"),
                         text_color="white", justify="center").pack(pady=(10, 4))
            ctk.CTkButton(nav, text="← Back to Main",
                          fg_color=NAV_HOV, hover_color=ACCENT,
                          text_color="white",
                          font=ctk.CTkFont("Segoe UI", 11, "bold"),
                          height=34, corner_radius=8,
                          command=back_cmd).pack(fill="x", padx=10, pady=(0, 6))
            ctk.CTkFrame(nav, height=1,
                         fg_color="#2F5496").pack(fill="x", padx=14, pady=(0, 4))
            scrl = ctk.CTkScrollableFrame(nav, fg_color="transparent",
                                          scrollbar_button_color=NAV_ACT,
                                          scrollbar_button_hover_color=NAV_HOV)
            scrl.pack(fill="both", expand=True)
            btns = {}
            for name in items:
                featured = (name == "Master Calc")
                b = ctk.CTkButton(scrl,
                                  text=("★  Master Calc" if featured else name),
                                  anchor="w",
                                  fg_color=NAV_ACT if featured else "transparent",
                                  hover_color=NAV_HOV, text_color="white",
                                  font=ctk.CTkFont("Segoe UI", 15 if featured else 13, "bold"),
                                  height=40 if featured else 30, corner_radius=6,
                                  command=lambda n=name: select_cmd(n))
                b.pack(fill="x", padx=8, pady=4 if featured else 1)
                btns[name] = b
            return nav, btns

        self._constr_nav, self._constr_btns = _make_nav(
            "Construction\nCalculators", self._exit_construction,
            ConstructionCalcTab.ALL_CALCS, self._select_constr)

        self._finance_nav, self._finance_btns = _make_nav(
            "Finance\nCalculators", self._exit_finance,
            FinanceCalcTab.ALL_CALCS, self._select_finance)

        self._it_nav, self._it_btns = _make_nav(
            "IT Networking\nCalculators", self._exit_it,
            ITNetworkingCalcTab.ALL_CALCS, self._select_it)

        self._conversion_nav, self._conversion_btns = _make_nav(
            "Conversion\nCalculators", self._exit_conversion,
            ConversionCalcTab.ALL_CALCS, self._select_conversion)

        self._electronics_nav, self._electronics_btns = _make_nav(
            "Electronics\nCalculators", self._exit_electronics,
            ElectronicsCalcTab.ALL_CALCS, self._select_electronics)

        self._medical_nav, self._medical_btns = _make_nav(
            "Medical\nCalculators", self._exit_medical,
            MedicalCalcTab.ALL_CALCS, self._select_medical)

    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color=APP_BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)
        # Only build tab 0 at startup -- all others built lazily on first click
        FrameClass = self.TABS[0][1]
        frame = FrameClass(self.content)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frames[0] = frame

    def _get_frame(self, idx, _place=True):
        # Build the frame lazily on first access.
        # _place=False lets _prebuild_tabs build invisibly in the background.
        if idx not in self._frames:
            _, FrameClass = self.TABS[idx]
            frame = FrameClass(self.content)
            self._frames[idx] = frame
        frame = self._frames[idx]
        if _place and not frame.place_info():
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        return frame

    def _prebuild_tabs(self):
        # Build one unbuilt tab per call, then schedule the next.
        # _place=False builds each frame invisibly -- no flash on screen.
        unbuilt = [i for i in range(len(self.TABS)) if i not in self._frames]
        if unbuilt:
            self._get_frame(unbuilt[0], _place=False)
            if len(unbuilt) > 1:
                self.after(50, self._prebuild_tabs)

    def _select(self, idx):
        # Deactivate the outgoing tab
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"):
                prev.deactivate()
        if self._active_btn is not None:
            self._active_btn.configure(fg_color="transparent")
        self._active_btn = self._nav_btns[idx]
        self._active_idx = idx
        self._active_btn.configure(fg_color=NAV_ACT)
        frame = self._get_frame(idx)
        frame.lift()
        # Activate the incoming tab
        if hasattr(frame, "activate"):
            frame.activate()

    def _enter_construction(self):
        """Switch sidebar to Construction Calculators view."""
        # Deactivate current tab
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        # Highlight Construction button (idx 3)
        constr_idx = next(i for i,(l,_) in enumerate(self.TABS) if "Construction" in l)
        self._nav_btns[constr_idx].configure(fg_color=NAV_ACT)
        self._active_idx = constr_idx
        # Show Construction frame in content (built lazily on first open)
        frame = self._get_frame(constr_idx)
        frame.lift()
        if hasattr(frame, "activate"):
            frame.activate()
        # Swap sidebar to construction nav
        self._main_nav.place_forget()
        self._constr_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        # Default to first calculator
        self._select_constr(ConstructionCalcTab.ALL_CALCS[0])

    def _exit_construction(self):
        """Return sidebar to main 4-button view."""
        self._constr_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        # Clear construction highlight
        for b in self._constr_btns.values():
            b.configure(fg_color="transparent")
        # Deactivate construction tab
        constr_idx = next(i for i,(l,_) in enumerate(self.TABS) if "Construction" in l)
        if hasattr(self._frames[constr_idx], "deactivate"):
            self._frames[constr_idx].deactivate()
        self._nav_btns[constr_idx].configure(fg_color="transparent")
        self._active_idx = None
        # Return to Basic Calculator
        self._select(0)

    def _select_constr(self, name):
        """Show a specific construction calculator."""
        for n, b in self._constr_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        constr_idx = next(i for i,(l,_) in enumerate(self.TABS) if "Construction" in l)
        frame = self._frames[constr_idx]
        if hasattr(frame, "show_calculator"):
            frame.show_calculator(name)


    def _enter_finance(self):
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Finance" in l)
        self._nav_btns[idx].configure(fg_color=NAV_ACT)
        self._active_idx = idx
        frame = self._get_frame(idx)
        frame.lift()
        if hasattr(frame, "activate"): frame.activate()
        self._main_nav.place_forget()
        self._finance_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._select_finance(FinanceCalcTab.ALL_CALCS[0])

    def _exit_finance(self):
        self._finance_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for b in self._finance_btns.values(): b.configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Finance" in l)
        if hasattr(self._frames[idx], "deactivate"): self._frames[idx].deactivate()
        self._nav_btns[idx].configure(fg_color="transparent")
        self._active_idx = None
        self._select(0)

    def _select_finance(self, name):
        for n, b in self._finance_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Finance" in l)
        if hasattr(self._frames[idx], "show_calculator"):
            self._frames[idx].show_calculator(name)

    def _enter_it(self):
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "IT Networking" in l)
        self._nav_btns[idx].configure(fg_color=NAV_ACT)
        self._active_idx = idx
        frame = self._get_frame(idx)
        frame.lift()
        if hasattr(frame, "activate"): frame.activate()
        self._main_nav.place_forget()
        self._it_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._select_it(ITNetworkingCalcTab.ALL_CALCS[0])

    def _exit_it(self):
        self._it_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for b in self._it_btns.values(): b.configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "IT Networking" in l)
        if hasattr(self._frames[idx], "deactivate"): self._frames[idx].deactivate()
        self._nav_btns[idx].configure(fg_color="transparent")
        self._active_idx = None
        self._select(0)

    def _select_it(self, name):
        for n, b in self._it_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "IT Networking" in l)
        if hasattr(self._frames[idx], "show_calculator"):
            self._frames[idx].show_calculator(name)



    def _enter_electronics(self):
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Electronics" in l)
        self._nav_btns[idx].configure(fg_color=NAV_ACT); self._active_idx = idx
        frame = self._get_frame(idx)
        frame.lift()
        if hasattr(frame, "activate"): frame.activate()
        self._main_nav.place_forget()
        self._electronics_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._select_electronics(ElectronicsCalcTab.ALL_CALCS[0])

    def _exit_electronics(self):
        self._electronics_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for b in self._electronics_btns.values(): b.configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Electronics" in l)
        if hasattr(self._frames[idx], "deactivate"): self._frames[idx].deactivate()
        self._nav_btns[idx].configure(fg_color="transparent")
        self._active_idx = None; self._select(0)

    def _select_electronics(self, name):
        for n, b in self._electronics_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Electronics" in l)
        if hasattr(self._frames[idx], "show_calculator"): self._frames[idx].show_calculator(name)

    def _enter_conversion(self):
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Conversion" in l)
        self._nav_btns[idx].configure(fg_color=NAV_ACT); self._active_idx = idx
        frame = self._get_frame(idx)
        frame.lift()
        if hasattr(frame, "activate"): frame.activate()
        self._main_nav.place_forget()
        self._conversion_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._select_conversion(ConversionCalcTab.ALL_CALCS[0])

    def _exit_conversion(self):
        self._conversion_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for b in self._conversion_btns.values(): b.configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Conversion" in l)
        if hasattr(self._frames[idx], "deactivate"): self._frames[idx].deactivate()
        self._nav_btns[idx].configure(fg_color="transparent")
        self._active_idx = None; self._select(0)

    def _select_conversion(self, name):
        for n, b in self._conversion_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Conversion" in l)
        if hasattr(self._frames[idx], "show_calculator"): self._frames[idx].show_calculator(name)

    def _enter_medical(self):
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, "deactivate"): prev.deactivate()
            self._nav_btns[self._active_idx].configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Medical" in l)
        self._nav_btns[idx].configure(fg_color=NAV_ACT); self._active_idx = idx
        frame = self._get_frame(idx)
        frame.lift()
        if hasattr(frame, "activate"): frame.activate()
        self._main_nav.place_forget()
        self._medical_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._select_medical(MedicalCalcTab.ALL_CALCS[0])

    def _exit_medical(self):
        self._medical_nav.place_forget()
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for b in self._medical_btns.values(): b.configure(fg_color="transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Medical" in l)
        if hasattr(self._frames[idx], "deactivate"): self._frames[idx].deactivate()
        self._nav_btns[idx].configure(fg_color="transparent")
        self._active_idx = None; self._select(0)

    def _select_medical(self, name):
        for n, b in self._medical_btns.items():
            b.configure(fg_color=NAV_ACT if n == name else "transparent")
        idx = next(i for i,(l,_) in enumerate(self.TABS) if "Medical" in l)
        if hasattr(self._frames[idx], "show_calculator"): self._frames[idx].show_calculator(name)


    # ════════════════════════════════════════════════════════════
    #  SETTINGS  (persistent prefs via hidden JSON file)
    # ════════════════════════════════════════════════════════════

    def _settings_path(self):
        base = os.path.dirname(
            sys.executable if getattr(sys, "frozen", False)
            else os.path.abspath(__file__))
        return os.path.join(base, "calculator_settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, prefs):
        try:
            path = self._settings_path()
            with open(path, "w") as f:
                json.dump(prefs, f, indent=2)
            # Hide the file on Windows so it does not clutter the user's folder
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 2)  # FILE_ATTRIBUTE_HIDDEN = 0x2
            except Exception:
                pass
        except Exception:
            pass

    def _apply_startup_settings(self):
        prefs = self._load_settings()
        if not prefs:
            return
        theme = prefs.get("theme", "Light")
        self._change_theme(theme)
        self.theme_var.set(theme)
        size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
        offset = size_map.get(prefs.get("font_size", "Default"), 0)
        if offset != 0:
            self._apply_font_offset(offset)
            self._font_offset = offset
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = {k: set(v) for k, v in prefs.get("hidden_sub", {}).items()}
        if hidden_mains or any(hidden_subs.values()):
            self._refresh_nav_visibility(hidden_mains, hidden_subs)
        default_tab    = prefs.get("default_tab", "")
        default_subtab = prefs.get("default_subtab", "— None —")
        if default_tab:
            self._navigate_to(default_tab, default_subtab)

    def _navigate_to(self, tab_label, subtab="— None —"):
        idx = next((i for i, (l, _) in enumerate(self.TABS) if l == tab_label), None)
        if idx is None:
            return
        sub = subtab if (subtab and subtab != "— None —") else None
        if "Construction" in tab_label:
            self._enter_construction()
            if sub: self._select_constr(sub)
        elif "Conversion" in tab_label:
            self._enter_conversion()
            if sub: self._select_conversion(sub)
        elif "Electronics" in tab_label:
            self._enter_electronics()
            if sub: self._select_electronics(sub)
        elif "Finance" in tab_label:
            self._enter_finance()
            if sub: self._select_finance(sub)
        elif "IT Networking" in tab_label:
            self._enter_it()
            if sub: self._select_it(sub)
        elif "Medical" in tab_label:
            self._enter_medical()
            if sub: self._select_medical(sub)
        else:
            self._select(idx)

    def _apply_font_offset(self, delta):
        seen = set()
        def walk(w):
            for child in w.winfo_children():
                try:
                    font = child.cget("font")
                    if isinstance(font, ctk.CTkFont):
                        fid = id(font)
                        if fid not in seen:
                            seen.add(fid)
                            cur = font.cget("size")
                            font.configure(size=max(6, cur + delta))
                    elif isinstance(font, tuple) and len(font) >= 2:
                        try:
                            new_size = max(6, int(font[1]) + delta)
                            child.configure(font=(font[0], new_size) + tuple(font[2:]))
                        except Exception:
                            pass
                except Exception:
                    pass
                walk(child)
        walk(self)

    def _refresh_nav_visibility(self, hidden_mains, hidden_subs):
        self._nav_sep.pack_forget()
        for btn in self._nav_btns:
            btn.pack_forget()
        for i, (lbl, _) in enumerate(self.TABS):
            if i == 2:
                self._nav_sep.pack(fill="x", padx=8, pady=(6, 6))
            if lbl not in hidden_mains:
                self._nav_btns[i].pack(fill="x", padx=12, pady=2)
        _drills = [
            ("Construction",  self._constr_btns),
            ("Conversion",    self._conversion_btns),
            ("Electronics",   self._electronics_btns),
            ("Finance",       self._finance_btns),
            ("IT Networking", self._it_btns),
            ("Medical",       self._medical_btns),
        ]
        for tab_key, btns_dict in _drills:
            tab_lbl = next((l for l, _ in self.TABS if tab_key in l), None)
            if tab_lbl is None:
                continue
            hidden_set = hidden_subs.get(tab_lbl, set())
            for name, btn in btns_dict.items():
                if name in hidden_set:
                    btn.pack_forget()
                else:
                    btn.pack(fill="x", padx=8, pady=1)

    def _open_about(self):
        # Build the about frame lazily the first time
        if not hasattr(self, '_about_frame'):
            self._build_about_frame()
        # Deactivate any highlighted nav button
        if self._active_btn is not None:
            self._active_btn.configure(fg_color='transparent')
            self._active_btn = None
        # Deactivate current calc frame
        if self._active_idx is not None:
            prev = self._frames.get(self._active_idx)
            if prev and hasattr(prev, 'deactivate'):
                prev.deactivate()
            self._active_idx = None
        # Restore main nav if a sub-nav (Construction, Finance, etc.) was active
        self._main_nav.place(relx=0, rely=0, relwidth=1, relheight=1)
        for _sub in ('_constr_nav', '_finance_nav', '_it_nav',
                     '_electronics_nav', '_conversion_nav', '_medical_nav'):
            _nav = getattr(self, _sub, None)
            if _nav:
                _nav.place_forget()
        self._about_frame.lift()

    def _build_about_frame(self):
        outer = ctk.CTkFrame(self.content, fg_color=APP_BG, corner_radius=0)
        outer.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._about_frame = outer

        scroll = ctk.CTkScrollableFrame(outer, fg_color=APP_BG,
                                        scrollbar_button_color=NAV_ACT,
                                        scrollbar_button_hover_color=NAV_HOV)
        scroll.pack(fill='both', expand=True)

        def lbl(parent, text, font_size=13, bold=False, color=None,
                wrap=900, pady=(0, 8), padx=28, anchor='w'):
            weight = 'bold' if bold else 'normal'
            ctk.CTkLabel(parent, text=text,
                         font=ctk.CTkFont('Segoe UI', font_size, weight),
                         text_color=color or TEXT,
                         justify='left', anchor=anchor,
                         wraplength=wrap).pack(
                             anchor='w', padx=padx, pady=pady)

        # ── About card ──────────────────────────────────────────────────
        card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill='x', padx=60, pady=(28, 14))

        lbl(card, 'Welcome! 👋', font_size=22, bold=True,
            color=NAV_BG, pady=(22, 10))

        lbl(card,
            'Beeran’s Calculator Suite was born from a simple idea — '
            'why juggle a dozen different tools when everything you need '
            'can live beautifully in one place?\n\n'
            'Whether you’re a contractor pricing a job, a nurse calculating '
            'a dosage, a developer subnetting a network, a student working '
            'through finances, or just splitting dinner with friends — '
            'this suite was thoughtfully built with you in mind.',
            pady=(0, 14))

        # stats strip
        stats = ctk.CTkFrame(card, fg_color=NAV_BG, corner_radius=8)
        stats.pack(fill='x', padx=28, pady=(0, 14))
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)
        stats.columnconfigure(2, weight=1)
        for col, (num, caption) in enumerate([
            ('50', 'Calculators'), ('8', 'Categories'), ('1', 'Beautiful Suite')
        ]):
            cell = ctk.CTkFrame(stats, fg_color='transparent')
            cell.grid(row=0, column=col, padx=8, pady=16, sticky='nsew')
            ctk.CTkLabel(cell, text=num,
                         font=ctk.CTkFont('Segoe UI', 32, 'bold'),
                         text_color='#90C8F0').pack()
            ctk.CTkLabel(cell, text=caption,
                         font=ctk.CTkFont('Segoe UI', 12),
                         text_color='white').pack()

        lbl(card,
            '📚  Categories:   Basic  ·  Scientific & Graphing  ·  '
            'Construction  ·  Conversion  ·  Electronics  ·  '
            'Finance  ·  IT Networking  ·  Medical',
            font_size=12, pady=(0, 16))

        # quote
        q = ctk.CTkFrame(card, fg_color=RES_BG, corner_radius=8)
        q.pack(fill='x', padx=28, pady=(0, 14))
        ctk.CTkLabel(q,
                     text=('“I wanted to bring many of the most popular everyday calculators '
                           'together in one beautiful, easy-to-use suite — '
                           'no ads, no subscriptions, no internet required. '
                           'Just the tools you need, right when you need them.”'),
                     font=ctk.CTkFont('Segoe UI', 13),
                     text_color=TEXT, justify='center',
                     wraplength=860).pack(padx=20, pady=14)

        ctk.CTkFrame(card, height=1,
                     fg_color=BORDER).pack(fill='x', padx=28, pady=(0, 10))
        lbl(card,
            '✨  Created by Beeran Rampersad  ·  Built with the assistance of Claude AI',
            font_size=12, color=MUTED, pady=(0, 22))

        # ── Suggestion card ─────────────────────────────────────────────
        scard = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        scard.pack(fill='x', padx=60, pady=(0, 14))

        lbl(scard, '💬  Got a Suggestion?',
            font_size=22, bold=True, color=NAV_BG, pady=(22, 10))

        lbl(scard,
            'This suite grows with its users!  If there’s a calculator '
            'you’d love to see, a feature that would make your day easier, '
            'or anything at all on your mind — we’d genuinely love to hear it.\n\n'
            'You never know… it just might show up in a future release! 😊',
            pady=(0, 12))

        # tk.Text is more reliable across CTk versions than CTkTextbox
        sug_box = tk.Text(scard, height=5,
                          font=('Segoe UI', 12),
                          fg=MUTED, bg=INPUT_BG,
                          relief='flat', wrap='word',
                          padx=10, pady=8,
                          insertbackground=TEXT,
                          selectbackground=ACCENT,
                          bd=1)
        sug_box.pack(fill='x', padx=28, pady=(0, 10))
        _PH = 'Write your thoughts here…'
        sug_box.insert('1.0', _PH)

        def _fi(e):
            if sug_box.get('1.0', 'end-1c') == _PH:
                sug_box.delete('1.0', 'end')
                sug_box.config(fg=TEXT)
        def _fo(e):
            if not sug_box.get('1.0', 'end-1c').strip():
                sug_box.insert('1.0', _PH)
                sug_box.config(fg=MUTED)
        sug_box.bind('<FocusIn>',  _fi)
        sug_box.bind('<FocusOut>', _fo)

        def _submit():
            msg = sug_box.get('1.0', 'end-1c').strip()
            if not msg or msg == _PH:
                sug_box.focus_set(); return
            import urllib.parse, webbrowser
            subj = urllib.parse.quote(
                'Beeran’s Calculator Suite — Suggestion / Enhancement')
            body = urllib.parse.quote(
                'Hi Beeran,\n\nI have a suggestion for the Calculator Suite:\n\n'
                + msg
                + f'\n\n—\nSent from Beeran’s Calculator Suite v{APP_VERSION}')
            webbrowser.open(
                f'mailto:CalculatorSuite@outlook.com?subject={subj}&body={body}')

        ctk.CTkButton(scard, text='📧  Submit Suggestion',
                      fg_color=ACCENT, hover_color=NAV_ACT,
                      text_color='white',
                      font=ctk.CTkFont('Segoe UI', 13, 'bold'),
                      height=42, corner_radius=8,
                      command=_submit).pack(
                          anchor='e', padx=28, pady=(0, 22))


        # -- PWA install guide
        pwa_card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
        pwa_card.pack(fill="x", padx=20, pady=(8, 4))
        ctk.CTkLabel(pwa_card,
                     text=chr(0x1F4F1)+"  Install as an App (PWA)",
                     font=ctk.CTkFont("Segoe UI", 16, "bold"),
                     text_color=ACCENT).pack(anchor="w", padx=20, pady=(16, 2))
        ctk.CTkLabel(pwa_card,
                     text=("A Progressive Web App "+chr(0x2014)+
                           " install from your browser. No App Store required."),
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 10))
        _sep = "- " * 20
        _pwa_lines = [
            _sep, "Android  (Chrome)", _sep,
            "1. Open Chrome on your Android device",
            "2. Go to beeranscalculatorsuite.com",
            "3. Three-dot menu at top-right",
            "4. Tap 'Add to Home screen' then Add",
            "   Opens fullscreen, works offline after install.", "",
            _sep, "iOS  (Safari only)", _sep,
            "1. Open Safari on your iPhone or iPad",
            "2. Go to beeranscalculatorsuite.com",
            "3. Share button at the bottom",
            "4. Scroll down, tap 'Add to Home Screen'",
            "   Note: Chrome on iOS does not support PWA install.", "",
            _sep, "Windows / Mac  (Chrome or Edge)", _sep,
            "1. Open Chrome or Edge",
            "2. Go to beeranscalculatorsuite.com",
            "3. Click the install icon in the address bar",
            "4. Click Install",
            "   If no icon: browser menu > Install app.", "",
            _sep, chr(0x1F504)+"  Keeping It Updated", _sep,
            "The app updates automatically in the background.", "",
            "To force a refresh:",
            "  Android/Desktop: Ctrl+Shift+R  (Cmd on Mac)",
            "  iOS: Delete from home screen, re-add via Safari", "",
            _sep, chr(0x1F4C4)+"  License", _sep,
            "MIT License -- free to use, modify, and distribute.",
            "Copyright 2026 Beeran Rampersad",
        ]
        _pwa_txt = chr(10).join(_pwa_lines)
        pwa_box = ctk.CTkTextbox(pwa_card, height=300,
                                 font=ctk.CTkFont("Segoe UI", 12),
                                 fg_color=INPUT_BG, text_color=TEXT,
                                 border_width=0, wrap="word")
        pwa_box.pack(fill="x", padx=16, pady=(0, 16))
        pwa_box.insert("1.0", _pwa_txt)
        pwa_box.configure(state="disabled")

        # ── Footer ──────────────────────────────────────────────────────
        ctk.CTkLabel(scroll,
                     text=(
                         f'Beeran’s Calculator Suite  ·  '
                         f'Version {APP_VERSION}  ·  '
                         '© 2026 Beeran Rampersad'),
                     font=ctk.CTkFont('Segoe UI', 11),
                     text_color=MUTED).pack(pady=(0, 20))

    def _open_settings(self):

        if hasattr(self, "_settings_win") and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        prefs = self._load_settings()
        win = ctk.CTkToplevel(self)
        self._settings_win = win
        win.title("⚙   Settings")
        win.geometry("540x720")
        win.minsize(480, 580)
        win.grab_set()
        win.configure(fg_color=APP_BG)
        win.update_idletasks()
        px, py = self.winfo_x(), self.winfo_y()
        pw, ph = self.winfo_width(), self.winfo_height()
        win.geometry(f"540x720+{px + (pw-540)//2}+{py + (ph-720)//2}")
        hdr = ctk.CTkFrame(win, fg_color=NAV_BG, corner_radius=0, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⚙   Settings",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color="white").pack(side="left", padx=22, pady=12)
        btn_bar = ctk.CTkFrame(win, fg_color=CARD, corner_radius=0,
                               height=62, border_width=1, border_color=BORDER)
        btn_bar.pack(fill="x", side="bottom")
        btn_bar.pack_propagate(False)
        scroll = ctk.CTkScrollableFrame(win, fg_color=APP_BG,
                                        scrollbar_button_color=NAV_ACT,
                                        scrollbar_button_hover_color=NAV_HOV)
        scroll.pack(fill="both", expand=True)
        def sec_hdr(title):
            f = ctk.CTkFrame(scroll, fg_color=NAV_BG, corner_radius=6, height=30)
            f.pack(fill="x", padx=16, pady=(14, 6))
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=title,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color="white").pack(side="left", padx=10)
        def card():
            f = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=8,
                             border_width=1, border_color=BORDER)
            f.pack(fill="x", padx=16, pady=(0, 4))
            return f
        sec_hdr("FONT SIZE")
        c = card()
        frow = ctk.CTkFrame(c, fg_color="transparent")
        frow.pack(fill="x", padx=14, pady=(12, 4))
        s_font = tk.StringVar(value=prefs.get("font_size", "Default"))
        for lbl, desc in [("Smaller", "−2 pt"), ("Default", "standard"), ("Larger", "+2 pt")]:
            col = ctk.CTkFrame(frow, fg_color="transparent")
            col.pack(side="left", padx=18)
            ctk.CTkRadioButton(col, text=lbl, variable=s_font, value=lbl,
                               font=ctk.CTkFont("Segoe UI", 13, "bold"),
                               text_color=TEXT,
                               fg_color=ACCENT, hover_color=NAV_ACT).pack()
            ctk.CTkLabel(col, text=desc,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=MUTED).pack()
        ctk.CTkLabel(c, text="Adjusts all fonts proportionally (takes effect immediately on Save).",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(2, 10), anchor="w")
        sec_hdr("STARTUP")
        c = card()
        tab_labels = [lbl for lbl, _ in self.TABS]
        r1 = ctk.CTkFrame(c, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(r1, text="Default Tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_tab = tk.StringVar(value=prefs.get("default_tab", tab_labels[0]))
        tab_menu = ctk.CTkOptionMenu(r1, values=tab_labels, variable=s_tab,
                                     fg_color=INPUT_BG, button_color=ACCENT,
                                     text_color=TEXT, dropdown_text_color=TEXT,
                                     font=ctk.CTkFont("Segoe UI", 13), width=210)
        tab_menu.pack(side="left")
        r2 = ctk.CTkFrame(c, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(r2, text="Default Sub-tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_subtab = tk.StringVar(value=prefs.get("default_subtab", "— None —"))
        subtab_menu = ctk.CTkOptionMenu(r2, values=["— None —"], variable=s_subtab,
                                        fg_color=INPUT_BG, button_color=ACCENT,
                                        text_color=TEXT, dropdown_text_color=TEXT,
                                        font=ctk.CTkFont("Segoe UI", 13), width=210)
        subtab_menu.pack(side="left")
        _SUB_MAP = {
            lbl: (getattr(cls, "ALL_CALCS", None) or [])
            for lbl, cls in self.TABS
        }
        def _refresh_subtab_menu(tab_lbl):
            subs = _SUB_MAP.get(tab_lbl, [])
            choices = ["— None —"] + list(subs)
            subtab_menu.configure(values=choices)
            if s_subtab.get() not in choices:
                s_subtab.set("— None —")
        s_tab.trace_add("write", lambda *_: _refresh_subtab_menu(s_tab.get()))
        _refresh_subtab_menu(s_tab.get())
        saved_st = prefs.get("default_subtab", "— None —")
        cur_subs = ["— None —"] + list(_SUB_MAP.get(s_tab.get(), []))
        if saved_st in cur_subs:
            s_subtab.set(saved_st)
        sec_hdr("VISIBLE CALCULATORS")
        c = card()
        ctk.CTkLabel(c, text="Uncheck items to hide them from the navigation sidebar.",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(8, 4), anchor="w")
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = prefs.get("hidden_sub", {})
        main_vars    = {}
        sub_vars     = {}
        for idx_t, (lbl, cls) in enumerate(self.TABS):
            bg = ALT_ROW if idx_t % 2 == 0 else CARD
            grp = ctk.CTkFrame(c, fg_color=bg, corner_radius=0)
            grp.pack(fill="x")
            mv = tk.BooleanVar(value=lbl not in hidden_mains)
            main_vars[lbl] = mv
            ctk.CTkCheckBox(grp, text=lbl, variable=mv,
                            font=ctk.CTkFont("Segoe UI", 13, "bold"),
                            text_color=TEXT, checkbox_width=16, checkbox_height=16,
                            checkmark_color="white", fg_color=ACCENT,
                            hover_color=NAV_ACT).pack(anchor="w", padx=14, pady=(6, 2))
            subs = getattr(cls, "ALL_CALCS", None) or []
            if subs:
                sub_vars[lbl] = {}
                hidden_sub_set = set(hidden_subs.get(lbl, []))
                sf = ctk.CTkFrame(grp, fg_color="transparent")
                sf.pack(fill="x", padx=28, pady=(0, 6))
                col0 = ctk.CTkFrame(sf, fg_color="transparent")
                col0.pack(side="left", fill="both", expand=True)
                col1 = ctk.CTkFrame(sf, fg_color="transparent")
                col1.pack(side="left", fill="both", expand=True)
                for k, name in enumerate(subs):
                    sv = tk.BooleanVar(value=name not in hidden_sub_set)
                    sub_vars[lbl][name] = sv
                    target = col0 if k % 2 == 0 else col1
                    ctk.CTkCheckBox(target, text=name, variable=sv,
                                    font=ctk.CTkFont("Segoe UI", 11),
                                    text_color=TEXT,
                                    checkbox_width=14, checkbox_height=14,
                                    checkmark_color="white", fg_color=ACCENT,
                                    hover_color=NAV_ACT).pack(anchor="w", padx=4, pady=1)
            else:
                ctk.CTkLabel(grp, text="(no sub-calculators)",
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=MUTED).pack(anchor="w", padx=30, pady=(0, 4))
            ctk.CTkFrame(c, height=1, fg_color=BORDER).pack(fill="x", padx=8)
        def _reset_all():
            s_theme.set("Light")
            s_font.set("Default")
            s_tab.set(tab_labels[0])
            s_subtab.set("— None —")
            for v in main_vars.values():
                v.set(True)
            for d in sub_vars.values():
                for v in d.values():
                    v.set(True)
        def _save_and_close():
            new_hidden_main = [lbl for lbl, v in main_vars.items() if not v.get()]
            new_hidden_sub  = {
                lbl: [n for n, v in d.items() if not v.get()]
                for lbl, d in sub_vars.items()
            }
            new_prefs = {
                "theme":          s_theme.get(),
                "font_size":      s_font.get(),
                "default_tab":    s_tab.get(),
                "default_subtab": s_subtab.get(),
                "hidden_main":    new_hidden_main,
                "hidden_sub":     {k: v for k, v in new_hidden_sub.items() if v},
            }
            self._save_settings(new_prefs)
            self._change_theme(new_prefs["theme"])
            self.theme_var.set(new_prefs["theme"])
            size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
            new_offset = size_map[new_prefs["font_size"]]
            delta = new_offset - self._font_offset
            if delta != 0:
                self._apply_font_offset(delta)
                self._font_offset = new_offset
            self._refresh_nav_visibility(
                set(new_prefs["hidden_main"]),
                {k: set(v) for k, v in new_prefs["hidden_sub"].items()},
            )
            win.destroy()
        ctk.CTkButton(btn_bar, text="Reset to Defaults",
                      fg_color="#718096", hover_color="#4A5568",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_reset_all).pack(side="left", padx=(16, 8), pady=11)
        ctk.CTkButton(btn_bar, text="Cancel",
                      fg_color="transparent", hover_color=BORDER,
                      text_color=MUTED,
                      font=ctk.CTkFont("Segoe UI", 12),
                      height=38, corner_radius=8,
                      command=win.destroy).pack(side="right", padx=(4, 16), pady=11)
        ctk.CTkButton(btn_bar, text="Save & Close",
                      fg_color=ACCENT, hover_color="#0D47A1",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_save_and_close).pack(side="right", padx=(4, 4), pady=11)

    # ════════════════════════════════════════════════════════════
    #  SETTINGS  (persistent prefs via hidden JSON file)
    # ════════════════════════════════════════════════════════════

    def _settings_path(self):
        base = os.path.dirname(
            sys.executable if getattr(sys, "frozen", False)
            else os.path.abspath(__file__))
        return os.path.join(base, "calculator_settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, prefs):
        try:
            path = self._settings_path()
            with open(path, "w") as f:
                json.dump(prefs, f, indent=2)
            # Hide the file on Windows so it does not clutter the user's folder
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 2)  # FILE_ATTRIBUTE_HIDDEN = 0x2
            except Exception:
                pass
        except Exception:
            pass

    def _apply_startup_settings(self):
        prefs = self._load_settings()
        if not prefs:
            return
        theme = prefs.get("theme", "Light")
        self._change_theme(theme)
        self.theme_var.set(theme)
        size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
        offset = size_map.get(prefs.get("font_size", "Default"), 0)
        if offset != 0:
            self._apply_font_offset(offset)
            self._font_offset = offset
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = {k: set(v) for k, v in prefs.get("hidden_sub", {}).items()}
        if hidden_mains or any(hidden_subs.values()):
            self._refresh_nav_visibility(hidden_mains, hidden_subs)
        default_tab    = prefs.get("default_tab", "")
        default_subtab = prefs.get("default_subtab", "— None —")
        if default_tab:
            self._navigate_to(default_tab, default_subtab)

    def _navigate_to(self, tab_label, subtab="— None —"):
        idx = next((i for i, (l, _) in enumerate(self.TABS) if l == tab_label), None)
        if idx is None:
            return
        sub = subtab if (subtab and subtab != "— None —") else None
        if "Construction" in tab_label:
            self._enter_construction()
            if sub: self._select_constr(sub)
        elif "Conversion" in tab_label:
            self._enter_conversion()
            if sub: self._select_conversion(sub)
        elif "Electronics" in tab_label:
            self._enter_electronics()
            if sub: self._select_electronics(sub)
        elif "Finance" in tab_label:
            self._enter_finance()
            if sub: self._select_finance(sub)
        elif "IT Networking" in tab_label:
            self._enter_it()
            if sub: self._select_it(sub)
        elif "Medical" in tab_label:
            self._enter_medical()
            if sub: self._select_medical(sub)
        else:
            self._select(idx)

    def _apply_font_offset(self, delta):
        seen = set()
        def walk(w):
            for child in w.winfo_children():
                try:
                    font = child.cget("font")
                    if isinstance(font, ctk.CTkFont):
                        fid = id(font)
                        if fid not in seen:
                            seen.add(fid)
                            cur = font.cget("size")
                            font.configure(size=max(6, cur + delta))
                    elif isinstance(font, tuple) and len(font) >= 2:
                        try:
                            new_size = max(6, int(font[1]) + delta)
                            child.configure(font=(font[0], new_size) + tuple(font[2:]))
                        except Exception:
                            pass
                except Exception:
                    pass
                walk(child)
        walk(self)

    def _refresh_nav_visibility(self, hidden_mains, hidden_subs):
        self._nav_sep.pack_forget()
        for btn in self._nav_btns:
            btn.pack_forget()
        for i, (lbl, _) in enumerate(self.TABS):
            if i == 2:
                self._nav_sep.pack(fill="x", padx=8, pady=(6, 6))
            if lbl not in hidden_mains:
                self._nav_btns[i].pack(fill="x", padx=12, pady=2)
        _drills = [
            ("Construction",  self._constr_btns),
            ("Conversion",    self._conversion_btns),
            ("Electronics",   self._electronics_btns),
            ("Finance",       self._finance_btns),
            ("IT Networking", self._it_btns),
            ("Medical",       self._medical_btns),
        ]
        for tab_key, btns_dict in _drills:
            tab_lbl = next((l for l, _ in self.TABS if tab_key in l), None)
            if tab_lbl is None:
                continue
            hidden_set = hidden_subs.get(tab_lbl, set())
            for name, btn in btns_dict.items():
                if name in hidden_set:
                    btn.pack_forget()
                else:
                    btn.pack(fill="x", padx=8, pady=1)

    def _open_settings(self):
        if hasattr(self, "_settings_win") and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        prefs = self._load_settings()
        win = ctk.CTkToplevel(self)
        self._settings_win = win
        win.title("⚙   Settings")
        win.geometry("540x720")
        win.minsize(480, 580)
        win.grab_set()
        win.configure(fg_color=APP_BG)
        win.update_idletasks()
        px, py = self.winfo_x(), self.winfo_y()
        pw, ph = self.winfo_width(), self.winfo_height()
        win.geometry(f"540x720+{px + (pw-540)//2}+{py + (ph-720)//2}")
        hdr = ctk.CTkFrame(win, fg_color=NAV_BG, corner_radius=0, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⚙   Settings",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color="white").pack(side="left", padx=22, pady=12)
        btn_bar = ctk.CTkFrame(win, fg_color=CARD, corner_radius=0,
                               height=62, border_width=1, border_color=BORDER)
        btn_bar.pack(fill="x", side="bottom")
        btn_bar.pack_propagate(False)
        scroll = ctk.CTkScrollableFrame(win, fg_color=APP_BG,
                                        scrollbar_button_color=NAV_ACT,
                                        scrollbar_button_hover_color=NAV_HOV)
        scroll.pack(fill="both", expand=True)
        def sec_hdr(title):
            f = ctk.CTkFrame(scroll, fg_color=NAV_BG, corner_radius=6, height=30)
            f.pack(fill="x", padx=16, pady=(14, 6))
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=title,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color="white").pack(side="left", padx=10)
        def card():
            f = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=8,
                             border_width=1, border_color=BORDER)
            f.pack(fill="x", padx=16, pady=(0, 4))
            return f
        sec_hdr("FONT SIZE")
        c = card()
        frow = ctk.CTkFrame(c, fg_color="transparent")
        frow.pack(fill="x", padx=14, pady=(12, 4))
        s_font = tk.StringVar(value=prefs.get("font_size", "Default"))
        for lbl, desc in [("Smaller", "−2 pt"), ("Default", "standard"), ("Larger", "+2 pt")]:
            col = ctk.CTkFrame(frow, fg_color="transparent")
            col.pack(side="left", padx=18)
            ctk.CTkRadioButton(col, text=lbl, variable=s_font, value=lbl,
                               font=ctk.CTkFont("Segoe UI", 13, "bold"),
                               text_color=TEXT,
                               fg_color=ACCENT, hover_color=NAV_ACT).pack()
            ctk.CTkLabel(col, text=desc,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=MUTED).pack()
        ctk.CTkLabel(c, text="Adjusts all fonts proportionally (takes effect immediately on Save).",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(2, 10), anchor="w")
        sec_hdr("STARTUP")
        c = card()
        tab_labels = [lbl for lbl, _ in self.TABS]
        r1 = ctk.CTkFrame(c, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(r1, text="Default Tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_tab = tk.StringVar(value=prefs.get("default_tab", tab_labels[0]))
        tab_menu = ctk.CTkOptionMenu(r1, values=tab_labels, variable=s_tab,
                                     fg_color=INPUT_BG, button_color=ACCENT,
                                     text_color=TEXT, dropdown_text_color=TEXT,
                                     font=ctk.CTkFont("Segoe UI", 13), width=210)
        tab_menu.pack(side="left")
        r2 = ctk.CTkFrame(c, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(r2, text="Default Sub-tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_subtab = tk.StringVar(value=prefs.get("default_subtab", "— None —"))
        subtab_menu = ctk.CTkOptionMenu(r2, values=["— None —"], variable=s_subtab,
                                        fg_color=INPUT_BG, button_color=ACCENT,
                                        text_color=TEXT, dropdown_text_color=TEXT,
                                        font=ctk.CTkFont("Segoe UI", 13), width=210)
        subtab_menu.pack(side="left")
        _SUB_MAP = {
            lbl: (getattr(cls, "ALL_CALCS", None) or [])
            for lbl, cls in self.TABS
        }
        def _refresh_subtab_menu(tab_lbl):
            subs = _SUB_MAP.get(tab_lbl, [])
            choices = ["— None —"] + list(subs)
            subtab_menu.configure(values=choices)
            if s_subtab.get() not in choices:
                s_subtab.set("— None —")
        s_tab.trace_add("write", lambda *_: _refresh_subtab_menu(s_tab.get()))
        _refresh_subtab_menu(s_tab.get())
        saved_st = prefs.get("default_subtab", "— None —")
        cur_subs = ["— None —"] + list(_SUB_MAP.get(s_tab.get(), []))
        if saved_st in cur_subs:
            s_subtab.set(saved_st)
        sec_hdr("VISIBLE CALCULATORS")
        c = card()
        ctk.CTkLabel(c, text="Uncheck items to hide them from the navigation sidebar.",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(8, 4), anchor="w")
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = prefs.get("hidden_sub", {})
        main_vars    = {}
        sub_vars     = {}
        for idx_t, (lbl, cls) in enumerate(self.TABS):
            bg = ALT_ROW if idx_t % 2 == 0 else CARD
            grp = ctk.CTkFrame(c, fg_color=bg, corner_radius=0)
            grp.pack(fill="x")
            mv = tk.BooleanVar(value=lbl not in hidden_mains)
            main_vars[lbl] = mv
            ctk.CTkCheckBox(grp, text=lbl, variable=mv,
                            font=ctk.CTkFont("Segoe UI", 13, "bold"),
                            text_color=TEXT, checkbox_width=16, checkbox_height=16,
                            checkmark_color="white", fg_color=ACCENT,
                            hover_color=NAV_ACT).pack(anchor="w", padx=14, pady=(6, 2))
            subs = getattr(cls, "ALL_CALCS", None) or []
            if subs:
                sub_vars[lbl] = {}
                hidden_sub_set = set(hidden_subs.get(lbl, []))
                sf = ctk.CTkFrame(grp, fg_color="transparent")
                sf.pack(fill="x", padx=28, pady=(0, 6))
                col0 = ctk.CTkFrame(sf, fg_color="transparent")
                col0.pack(side="left", fill="both", expand=True)
                col1 = ctk.CTkFrame(sf, fg_color="transparent")
                col1.pack(side="left", fill="both", expand=True)
                for k, name in enumerate(subs):
                    sv = tk.BooleanVar(value=name not in hidden_sub_set)
                    sub_vars[lbl][name] = sv
                    target = col0 if k % 2 == 0 else col1
                    ctk.CTkCheckBox(target, text=name, variable=sv,
                                    font=ctk.CTkFont("Segoe UI", 11),
                                    text_color=TEXT,
                                    checkbox_width=14, checkbox_height=14,
                                    checkmark_color="white", fg_color=ACCENT,
                                    hover_color=NAV_ACT).pack(anchor="w", padx=4, pady=1)
            else:
                ctk.CTkLabel(grp, text="(no sub-calculators)",
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=MUTED).pack(anchor="w", padx=30, pady=(0, 4))
            ctk.CTkFrame(c, height=1, fg_color=BORDER).pack(fill="x", padx=8)
        def _reset_all():
            s_theme.set("Light")
            s_font.set("Default")
            s_tab.set(tab_labels[0])
            s_subtab.set("— None —")
            for v in main_vars.values():
                v.set(True)
            for d in sub_vars.values():
                for v in d.values():
                    v.set(True)
        def _save_and_close():
            new_hidden_main = [lbl for lbl, v in main_vars.items() if not v.get()]
            new_hidden_sub  = {
                lbl: [n for n, v in d.items() if not v.get()]
                for lbl, d in sub_vars.items()
            }
            new_prefs = {
                "theme":          s_theme.get(),
                "font_size":      s_font.get(),
                "default_tab":    s_tab.get(),
                "default_subtab": s_subtab.get(),
                "hidden_main":    new_hidden_main,
                "hidden_sub":     {k: v for k, v in new_hidden_sub.items() if v},
            }
            self._save_settings(new_prefs)
            self._change_theme(new_prefs["theme"])
            self.theme_var.set(new_prefs["theme"])
            size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
            new_offset = size_map[new_prefs["font_size"]]
            delta = new_offset - self._font_offset
            if delta != 0:
                self._apply_font_offset(delta)
                self._font_offset = new_offset
            self._refresh_nav_visibility(
                set(new_prefs["hidden_main"]),
                {k: set(v) for k, v in new_prefs["hidden_sub"].items()},
            )
            win.destroy()
        ctk.CTkButton(btn_bar, text="Reset to Defaults",
                      fg_color="#718096", hover_color="#4A5568",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_reset_all).pack(side="left", padx=(16, 8), pady=11)
        ctk.CTkButton(btn_bar, text="Cancel",
                      fg_color="transparent", hover_color=BORDER,
                      text_color=MUTED,
                      font=ctk.CTkFont("Segoe UI", 12),
                      height=38, corner_radius=8,
                      command=win.destroy).pack(side="right", padx=(4, 16), pady=11)
        ctk.CTkButton(btn_bar, text="Save & Close",
                      fg_color=ACCENT, hover_color="#0D47A1",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_save_and_close).pack(side="right", padx=(4, 4), pady=11)

    # ════════════════════════════════════════════════════════════
    #  SETTINGS  (persistent prefs via hidden JSON file)
    # ════════════════════════════════════════════════════════════

    def _settings_path(self):
        base = os.path.dirname(
            sys.executable if getattr(sys, "frozen", False)
            else os.path.abspath(__file__))
        return os.path.join(base, "calculator_settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, prefs):
        try:
            path = self._settings_path()
            with open(path, "w") as f:
                json.dump(prefs, f, indent=2)
            # Hide the file on Windows so it does not clutter the user's folder
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 2)  # FILE_ATTRIBUTE_HIDDEN = 0x2
            except Exception:
                pass
        except Exception:
            pass

    def _apply_startup_settings(self):
        prefs = self._load_settings()
        if not prefs:
            return
        theme = prefs.get("theme", "Light")
        self._change_theme(theme)
        self.theme_var.set(theme)
        size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
        offset = size_map.get(prefs.get("font_size", "Default"), 0)
        if offset != 0:
            self._apply_font_offset(offset)
            self._font_offset = offset
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = {k: set(v) for k, v in prefs.get("hidden_sub", {}).items()}
        if hidden_mains or any(hidden_subs.values()):
            self._refresh_nav_visibility(hidden_mains, hidden_subs)
        default_tab    = prefs.get("default_tab", "")
        default_subtab = prefs.get("default_subtab", "— None —")
        if default_tab:
            self._navigate_to(default_tab, default_subtab)

    def _navigate_to(self, tab_label, subtab="— None —"):
        idx = next((i for i, (l, _) in enumerate(self.TABS) if l == tab_label), None)
        if idx is None:
            return
        sub = subtab if (subtab and subtab != "— None —") else None
        if "Construction" in tab_label:
            self._enter_construction()
            if sub: self._select_constr(sub)
        elif "Conversion" in tab_label:
            self._enter_conversion()
            if sub: self._select_conversion(sub)
        elif "Electronics" in tab_label:
            self._enter_electronics()
            if sub: self._select_electronics(sub)
        elif "Finance" in tab_label:
            self._enter_finance()
            if sub: self._select_finance(sub)
        elif "IT Networking" in tab_label:
            self._enter_it()
            if sub: self._select_it(sub)
        elif "Medical" in tab_label:
            self._enter_medical()
            if sub: self._select_medical(sub)
        else:
            self._select(idx)

    def _apply_font_offset(self, delta):
        seen = set()
        def walk(w):
            for child in w.winfo_children():
                try:
                    font = child.cget("font")
                    if isinstance(font, ctk.CTkFont):
                        fid = id(font)
                        if fid not in seen:
                            seen.add(fid)
                            cur = font.cget("size")
                            font.configure(size=max(6, cur + delta))
                    elif isinstance(font, tuple) and len(font) >= 2:
                        try:
                            new_size = max(6, int(font[1]) + delta)
                            child.configure(font=(font[0], new_size) + tuple(font[2:]))
                        except Exception:
                            pass
                except Exception:
                    pass
                walk(child)
        walk(self)

    def _refresh_nav_visibility(self, hidden_mains, hidden_subs):
        self._nav_sep.pack_forget()
        for btn in self._nav_btns:
            btn.pack_forget()
        for i, (lbl, _) in enumerate(self.TABS):
            if i == 2:
                self._nav_sep.pack(fill="x", padx=8, pady=(6, 6))
            if lbl not in hidden_mains:
                self._nav_btns[i].pack(fill="x", padx=12, pady=2)
        _drills = [
            ("Construction",  self._constr_btns),
            ("Conversion",    self._conversion_btns),
            ("Electronics",   self._electronics_btns),
            ("Finance",       self._finance_btns),
            ("IT Networking", self._it_btns),
            ("Medical",       self._medical_btns),
        ]
        for tab_key, btns_dict in _drills:
            tab_lbl = next((l for l, _ in self.TABS if tab_key in l), None)
            if tab_lbl is None:
                continue
            hidden_set = hidden_subs.get(tab_lbl, set())
            for name, btn in btns_dict.items():
                if name in hidden_set:
                    btn.pack_forget()
                else:
                    btn.pack(fill="x", padx=8, pady=1)

    def _open_settings(self):
        if hasattr(self, "_settings_win") and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        prefs = self._load_settings()
        win = ctk.CTkToplevel(self)
        self._settings_win = win
        win.title("⚙   Settings")
        win.geometry("540x720")
        win.minsize(480, 580)
        win.grab_set()
        win.configure(fg_color=APP_BG)
        win.update_idletasks()
        px, py = self.winfo_x(), self.winfo_y()
        pw, ph = self.winfo_width(), self.winfo_height()
        win.geometry(f"540x720+{px + (pw-540)//2}+{py + (ph-720)//2}")
        hdr = ctk.CTkFrame(win, fg_color=NAV_BG, corner_radius=0, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⚙   Settings",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color="white").pack(side="left", padx=22, pady=12)
        btn_bar = ctk.CTkFrame(win, fg_color=CARD, corner_radius=0,
                               height=62, border_width=1, border_color=BORDER)
        btn_bar.pack(fill="x", side="bottom")
        btn_bar.pack_propagate(False)
        scroll = ctk.CTkScrollableFrame(win, fg_color=APP_BG,
                                        scrollbar_button_color=NAV_ACT,
                                        scrollbar_button_hover_color=NAV_HOV)
        scroll.pack(fill="both", expand=True)
        def sec_hdr(title):
            f = ctk.CTkFrame(scroll, fg_color=NAV_BG, corner_radius=6, height=30)
            f.pack(fill="x", padx=16, pady=(14, 6))
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=title,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color="white").pack(side="left", padx=10)
        def card():
            f = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=8,
                             border_width=1, border_color=BORDER)
            f.pack(fill="x", padx=16, pady=(0, 4))
            return f
        sec_hdr("FONT SIZE")
        c = card()
        frow = ctk.CTkFrame(c, fg_color="transparent")
        frow.pack(fill="x", padx=14, pady=(12, 4))
        s_font = tk.StringVar(value=prefs.get("font_size", "Default"))
        for lbl, desc in [("Smaller", "−2 pt"), ("Default", "standard"), ("Larger", "+2 pt")]:
            col = ctk.CTkFrame(frow, fg_color="transparent")
            col.pack(side="left", padx=18)
            ctk.CTkRadioButton(col, text=lbl, variable=s_font, value=lbl,
                               font=ctk.CTkFont("Segoe UI", 13, "bold"),
                               text_color=TEXT,
                               fg_color=ACCENT, hover_color=NAV_ACT).pack()
            ctk.CTkLabel(col, text=desc,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=MUTED).pack()
        ctk.CTkLabel(c, text="Adjusts all fonts proportionally (takes effect immediately on Save).",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(2, 10), anchor="w")
        sec_hdr("STARTUP")
        c = card()
        tab_labels = [lbl for lbl, _ in self.TABS]
        r1 = ctk.CTkFrame(c, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(r1, text="Default Tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_tab = tk.StringVar(value=prefs.get("default_tab", tab_labels[0]))
        tab_menu = ctk.CTkOptionMenu(r1, values=tab_labels, variable=s_tab,
                                     fg_color=INPUT_BG, button_color=ACCENT,
                                     text_color=TEXT, dropdown_text_color=TEXT,
                                     font=ctk.CTkFont("Segoe UI", 13), width=210)
        tab_menu.pack(side="left")
        r2 = ctk.CTkFrame(c, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(r2, text="Default Sub-tab:",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=TEXT, width=150, anchor="w").pack(side="left")
        s_subtab = tk.StringVar(value=prefs.get("default_subtab", "— None —"))
        subtab_menu = ctk.CTkOptionMenu(r2, values=["— None —"], variable=s_subtab,
                                        fg_color=INPUT_BG, button_color=ACCENT,
                                        text_color=TEXT, dropdown_text_color=TEXT,
                                        font=ctk.CTkFont("Segoe UI", 13), width=210)
        subtab_menu.pack(side="left")
        _SUB_MAP = {
            lbl: (getattr(cls, "ALL_CALCS", None) or [])
            for lbl, cls in self.TABS
        }
        def _refresh_subtab_menu(tab_lbl):
            subs = _SUB_MAP.get(tab_lbl, [])
            choices = ["— None —"] + list(subs)
            subtab_menu.configure(values=choices)
            if s_subtab.get() not in choices:
                s_subtab.set("— None —")
        s_tab.trace_add("write", lambda *_: _refresh_subtab_menu(s_tab.get()))
        _refresh_subtab_menu(s_tab.get())
        saved_st = prefs.get("default_subtab", "— None —")
        cur_subs = ["— None —"] + list(_SUB_MAP.get(s_tab.get(), []))
        if saved_st in cur_subs:
            s_subtab.set(saved_st)
        sec_hdr("VISIBLE CALCULATORS")
        c = card()
        ctk.CTkLabel(c, text="Uncheck items to hide them from the navigation sidebar.",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=MUTED).pack(padx=14, pady=(8, 4), anchor="w")
        hidden_mains = set(prefs.get("hidden_main", []))
        hidden_subs  = prefs.get("hidden_sub", {})
        main_vars    = {}
        sub_vars     = {}
        for idx_t, (lbl, cls) in enumerate(self.TABS):
            bg = ALT_ROW if idx_t % 2 == 0 else CARD
            grp = ctk.CTkFrame(c, fg_color=bg, corner_radius=0)
            grp.pack(fill="x")
            mv = tk.BooleanVar(value=lbl not in hidden_mains)
            main_vars[lbl] = mv
            ctk.CTkCheckBox(grp, text=lbl, variable=mv,
                            font=ctk.CTkFont("Segoe UI", 13, "bold"),
                            text_color=TEXT, checkbox_width=16, checkbox_height=16,
                            checkmark_color="white", fg_color=ACCENT,
                            hover_color=NAV_ACT).pack(anchor="w", padx=14, pady=(6, 2))
            subs = getattr(cls, "ALL_CALCS", None) or []
            if subs:
                sub_vars[lbl] = {}
                hidden_sub_set = set(hidden_subs.get(lbl, []))
                sf = ctk.CTkFrame(grp, fg_color="transparent")
                sf.pack(fill="x", padx=28, pady=(0, 6))
                col0 = ctk.CTkFrame(sf, fg_color="transparent")
                col0.pack(side="left", fill="both", expand=True)
                col1 = ctk.CTkFrame(sf, fg_color="transparent")
                col1.pack(side="left", fill="both", expand=True)
                for k, name in enumerate(subs):
                    sv = tk.BooleanVar(value=name not in hidden_sub_set)
                    sub_vars[lbl][name] = sv
                    target = col0 if k % 2 == 0 else col1
                    ctk.CTkCheckBox(target, text=name, variable=sv,
                                    font=ctk.CTkFont("Segoe UI", 11),
                                    text_color=TEXT,
                                    checkbox_width=14, checkbox_height=14,
                                    checkmark_color="white", fg_color=ACCENT,
                                    hover_color=NAV_ACT).pack(anchor="w", padx=4, pady=1)
            else:
                ctk.CTkLabel(grp, text="(no sub-calculators)",
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=MUTED).pack(anchor="w", padx=30, pady=(0, 4))
            ctk.CTkFrame(c, height=1, fg_color=BORDER).pack(fill="x", padx=8)
        def _reset_all():
            s_theme.set("Light")
            s_font.set("Default")
            s_tab.set(tab_labels[0])
            s_subtab.set("— None —")
            for v in main_vars.values():
                v.set(True)
            for d in sub_vars.values():
                for v in d.values():
                    v.set(True)
        def _save_and_close():
            new_hidden_main = [lbl for lbl, v in main_vars.items() if not v.get()]
            new_hidden_sub  = {
                lbl: [n for n, v in d.items() if not v.get()]
                for lbl, d in sub_vars.items()
            }
            new_prefs = {
                "theme":          s_theme.get(),
                "font_size":      s_font.get(),
                "default_tab":    s_tab.get(),
                "default_subtab": s_subtab.get(),
                "hidden_main":    new_hidden_main,
                "hidden_sub":     {k: v for k, v in new_hidden_sub.items() if v},
            }
            self._save_settings(new_prefs)
            self._change_theme(new_prefs["theme"])
            self.theme_var.set(new_prefs["theme"])
            size_map = {"Smaller": -2, "Default": 0, "Larger": 2}
            new_offset = size_map[new_prefs["font_size"]]
            delta = new_offset - self._font_offset
            if delta != 0:
                self._apply_font_offset(delta)
                self._font_offset = new_offset
            self._refresh_nav_visibility(
                set(new_prefs["hidden_main"]),
                {k: set(v) for k, v in new_prefs["hidden_sub"].items()},
            )
            win.destroy()
        ctk.CTkButton(btn_bar, text="Reset to Defaults",
                      fg_color="#718096", hover_color="#4A5568",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_reset_all).pack(side="left", padx=(16, 8), pady=11)
        ctk.CTkButton(btn_bar, text="Cancel",
                      fg_color="transparent", hover_color=BORDER,
                      text_color=MUTED,
                      font=ctk.CTkFont("Segoe UI", 12),
                      height=38, corner_radius=8,
                      command=win.destroy).pack(side="right", padx=(4, 16), pady=11)
        ctk.CTkButton(btn_bar, text="Save & Close",
                      fg_color=ACCENT, hover_color="#0D47A1",
                      text_color="white",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      height=38, corner_radius=8,
                      command=_save_and_close).pack(side="right", padx=(4, 4), pady=11)

    def _on_close(self):
        self.withdraw()
        self.quit()


if __name__ == "__main__":
    app = App()
    app.mainloop()
