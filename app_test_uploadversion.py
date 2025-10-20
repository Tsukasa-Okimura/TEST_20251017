from flask import Flask, request, redirect, url_for, render_template_string, session, make_response
import re

app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret"

# 数値フィールドの下限
NUMBER_MIN = {
    "B": 0, "C": 1, "M": 0, "N": 0,
    "X1": 0, "X5": 0, "X6": 0,
    "E": 0, "F": 0, "G": 0, "H": 0, "I": 0, "J": 0
}

# E〜J は 0/1 入力（なし=0, あり=1）
YN_FIELDS = {"E", "F", "G", "H", "I", "J"}

# 受け付けるキー（添付txtのラベル中の（A）などを抽出）
ALL_KEYS = [
    "A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U",
    "X1","X2","X3","X4","X5","X6","X7","X8","X9"
]

def yes_no_text(v, yes="あり", no="なし"):
    return yes if str(v).strip() == "1" else no

def to_int_floor(val, default=0, min_value=0):
    try:
        n = int(str(val).strip())
    except Exception:
        n = default
    if n < min_value:
        n = min_value
    return n

def format_month(ym_str):
    """'YYYY-MM' または 'YYYY年MM月' を 'YYYY年M月' に正規化"""
    s = (ym_str or "").strip()
    if not s:
        return s
    # すでに 'YYYY年MM月' 形式
    m = re.match(r"^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y}年{mo}月"
    # 'YYYY-MM' 形式
    m = re.match(r"^\s*(\d{4})-(\d{1,2})\s*$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y}年{mo}月"
    # それ以外はそのまま返す
    return s

def parse_uploaded_txt(text):
    """
    添付txtの想定構成：
      見出し（〜（A））の行 → 次の非空行が値
      複数行でも、最初の非空1行を値として採用
    """
    vals = {k: "" for k in ALL_KEYS}
    lines = text.splitlines()
    current_key = None
    want_value = False

    key_pat = re.compile(r"（\s*([A-Z]\d?)\s*）")  # 全角カッコ内のキーを取得（A, X1 など）

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m = key_pat.search(line)
        if m:
            # ラベル行
            k = m.group(1)
            # キーを A, X1 などに正規化
            if k in ALL_KEYS:
                current_key = k
                want_value = True
            else:
                current_key = None
                want_value = False
            continue

        if want_value and current_key:
            vals[current_key] = line
            current_key = None
            want_value = False

    # 数値の正規化
    for k, mn in NUMBER_MIN.items():
        vals[k] = str(to_int_floor(vals.get(k, ""), default=mn, min_value=mn))

    # E〜J の 0/1 を一応0/1に丸め
    for k in YN_FIELDS:
        vals[k] = "1" if str(vals.get(k, "0")).strip() == "1" else "0"

    return vals

def build_text(vals):
    # --- 兄弟人数 ---
    if vals.get("B", "1") == "1":
        sibling_text = "出生。同胞なし。"
    else:
        sibling_text = f"同胞{vals['B']}人の第{vals['C']}子として出生。"

    # --- 入院歴 ---
    if vals.get("X5", "0") == "0":
        hospital_text = "入院歴なし。"
    else:
        hospital_text = f"入院歴は{vals['X5']}回ある。"

    # --- 転院回数 ---
    if vals.get("X6", "0") == "0":
        transfer_text = f"{hospital_text}その後、転院したことはない。"
    else:
        transfer_text = f"{hospital_text}その後、{vals['X6']}回転院したことがある。"

    # --- 精神科通院 ---
    if vals.get("X1", "0") == "0":
        psych_text = "精神科への通院歴はこれまでなし。"
    else:
        psych_text = (
            f"精神科への通院は{vals['X1']}歳からで、理由は{vals['X2']}のため。"
            f"{vals['X3']}に受診し、{vals['X4']}と診断された。"
            f"{transfer_text}"
        )

    # --- E〜J 0/1 → あり/なし ---
    e_text = yes_no_text(vals["E"], "いじめあり", "いじめなし")
    f_text = yes_no_text(vals["F"], "不登校あり", "不登校なし")
    g_text = yes_no_text(vals["G"], "いじめあり", "いじめなし")
    h_text = yes_no_text(vals["H"], "不登校あり", "不登校なし")
    i_text = yes_no_text(vals["I"], "いじめあり", "いじめなし")
    j_text = yes_no_text(vals["J"], "不登校あり", "不登校なし")

    # --- X7：YYYY-MM / YYYY年MM月 → 日本語年月へ ---
    x7_jp = format_month(vals.get("X7", ""))

    # --- 発症文：X7頃から、X9のきっかけで、X8が出現した。 ---
    onset_text = ""
    if vals.get("X7") or vals.get("X8") or vals.get("X9"):
        onset_text = f"{x7_jp}頃から、{vals.get('X9','')}のきっかけで、{vals.get('X8','')}が出現した。"

    # --- 全体テキスト ---
    text = (
f"【生活歴】\n"
f"{vals['A']}にて{sibling_text}"
f"発達の遅れや異常については{vals['D']}。 "
f"小学校では{e_text}、{f_text}。 "
f"中学校では{g_text}、{h_text}。 "
f"高校では{i_text}、{j_text}。 "
f"最終学歴は、{vals['K']}。卒業後は{vals['L']}に就職。 "
f"{vals['M']}歳で結婚。子供は{vals['N']}人。離婚は{vals['O']}。 "
f"現在は{vals['P']}と{vals['Q']}にて生活。\n"
f"【現病歴】\n"
f"{psych_text}"
f"{onset_text}\n"
f"【既往歴】{vals['T']}\n"
f"【家族歴】{vals['U']}\n"
f"【喫煙歴】{vals['S']}\n"
f"【飲酒歴】{vals['R']}\n"
    )
    return text

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("txtfile")
        if not file or file.filename == "":
            return render_template_string("<p>ファイルが選択されていません。</p><p><a href='/upload'>戻る</a></p>")
        text = file.read().decode("utf-8", errors="ignore")
        vals = parse_uploaded_txt(text)
        # セッションに保存
        for k, v in vals.items():
            session[k] = v
        return redirect(url_for("output_page"))

    # GET: アップロードフォーム
    return render_template_string("""
<h2>入力テキスト（.txt）をアップロード</h2>
<form method="post" enctype="multipart/form-data" style="line-height:1.9;">
  <input type="file" name="txtfile" accept=".txt" required>
  <button type="submit">送信</button>
</form>
<p style="margin-top:12px;">※ 添付の見出し付きフォーマット（（A）〜（X9））に対応しています。</p>
<p><a href="/output">出力ページを見る</a></p>
""")

@app.route("/output")
def output_page():
    # 最低限 A が空なら未読込と判断
    if not session.get("A"):
        return render_template_string("""
<p>まだテキストが読み込まれていません。</p>
<p><a href="/upload">アップロードページへ</a></p>
""")
    vals = {k: session.get(k, "") for k in ALL_KEYS}
    text = build_text(vals)
    return render_template_string("""
<h2>自動生成テキスト</h2>
<div style="white-space:pre-wrap; border:1px solid #ccc; padding:12px; border-radius:8px; text-align:left;">
{{- text -}}
</div>
<p style="margin-top:12px;">
  <a href="/upload">別ファイルでやり直す</a> |
  <a href="/download">テキストを保存</a> |
  <a href="/reset">入力をリセット</a>
</p>
""", text=text)

@app.route("/download")
def download_txt():
    if not session.get("A"):
        return redirect(url_for("upload"))
    vals = {k: session.get(k, "") for k in ALL_KEYS}
    text = build_text(vals)
    resp = make_response(text)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="seikatsu_genbyoreki.txt"'
    return resp

@app.route("/reset")
def reset():
    for k in list(session.keys()):
        session.pop(k, None)
    return redirect(url_for("upload"))

@app.route("/")
def root():
    return redirect(url_for("upload"))

if __name__ == "__main__":
    app.run(debug=True)
