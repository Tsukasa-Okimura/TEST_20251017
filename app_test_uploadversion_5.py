from flask import Flask, request, redirect, url_for, render_template_string, session, make_response
import re

app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret"

# 全角数字 → 半角数字 変換用テーブル
FW_TO_HW = str.maketrans("０１２３４５６７８９", "0123456789")

# 数値フィールドの下限（旧フォーマット用）
NUMBER_MIN = {
    "B": 0, "C": 1, "M": 0, "N": 0,
    "X1": 0, "X5": 0, "X6": 0,
    "E": 0, "F": 0, "G": 0, "H": 0, "I": 0, "J": 0
}

# E〜J は 0/1 入力（なし=0, あり=1）（旧フォーマット用）
YN_FIELDS = {"E", "F", "G", "H", "I", "J"}

# input_for_4 の先頭にあるヘッダ行（使わないので無視する：旧フォーマット用）
SKIP_HEADER_PREFIXES = (
    "【診療科】",
    "【予約日時】",
    "【名前】",
    "【住所】",
    "【電話番号】",
    "【性別】",
)

# 空なら 'X' に置き換えるヘルパー
def val_or_x(v):
    s = "" if v is None else str(v).strip()
    return s if s else "X"

# 旧フォーマットで受け付けるキー
ALL_KEYS_OLD = [
    "A","B","C","D","E","F","G","H","I","J",
    "K","L","M","N","O","P","Q","R","S","T","U",
    "X1","X2","X3","X4","X5","X6","X7",
    "X8","X9","X10"
]

# 新フォーマットで使うキー
# A,B,C,D,E,F,G,H は新フォーマット用の意味
# X1〜X8 は家族歴〜備考
ALL_KEYS_NEW = [
    "A", "B", "C", "D", "E", "F", "G", "H",
    "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8"
]

def yes_no_text(v, yes="あり", no="なし", unknown="X"):
    s = "" if v is None else str(v).strip()
    s = s.translate(FW_TO_HW)
    if s == "1":
        return yes
    if s == "0":
        return no
    return unknown

def to_int_floor(val, default=0, min_value=0):
    """先頭に現れる整数部分だけを数値として解釈（全角対応）。"""
    try:
        s = str(val).strip().translate(FW_TO_HW)
        m = re.search(r"-?\d+", s)
        if not m:
            raise ValueError
        n = int(m.group(0))
    except Exception:
        n = default
    if n < min_value:
        n = min_value
    return n

def format_month(ym_str):
    """'YYYY年MM月(ごろ等...)' または 'YYYY-MM' を 'YYYY年M月' に正規化。
    解釈できない、または未入力なら 'X' を返す。（旧フォーマット X8 用）"""
    s = (ym_str or "").strip()
    if not s:
        return "X"
    # 文中から 'YYYY年MM月' を抜き出す（「ごろ」などが後ろについていてもOK）
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y}年{mo}月"
    # 'YYYY-MM' 形式
    m = re.match(r"^\s*(\d{4})-(\d{1,2})\s*$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y}年{mo}月"
    # それ以外は解釈不能として 'X'
    return "X"

# ===============================
# 旧フォーマット用パーサー
# ===============================
def parse_uploaded_txt_old(text):
    """
    旧フォーマット想定：
      1) 【〜（A）】        ←ラベルだけ（次の行に値）
      2) 【〜（A）】 値     ← ラベルと値が同じ行
      3) 【〜（E） 0=なし / 1=あり】 0
         のように説明が入っていても、最後の「】」以降を値として読む
    """
    vals = {k: "" for k in ALL_KEYS_OLD}
    lines = text.splitlines()
    current_key = None
    want_value = False

    # ★全角（ ）と半角 () の両方を許容
    key_pat = re.compile(r"[（(]\s*([A-Z]\d{0,2})\s*[）)]")

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # 先頭のヘッダ（診療科・予約日時・名前・住所・電話番号・性別）は無視
        if any(line.startswith(p) for p in SKIP_HEADER_PREFIXES):
            continue

        m = key_pat.search(line)
        if m:
            # ラベル行
            k = m.group(1)
            if k in ALL_KEYS_OLD:
                current_key = k
                # ★値が同じ行にあるか確認：最後の「】」以降を値とみなす
                idx = line.rfind("】")
                value_on_line = ""
                if idx != -1 and idx + 1 < len(line):
                    value_on_line = line[idx+1:].strip()
                if value_on_line:
                    # 同じ行に値がある
                    vals[k] = value_on_line
                    current_key = None
                    want_value = False
                else:
                    # 次の行で値を読む
                    want_value = True
            else:
                current_key = None
                want_value = False
            continue

        # 直前にラベルが出ていて、まだ値を読んでいない場合
        if want_value and current_key:
            vals[current_key] = line
            current_key = None
            want_value = False

    # 数値の正規化（入力が空ならそのまま＝未入力）
    for k, mn in NUMBER_MIN.items():
        raw = vals.get(k, "")
        if str(raw).strip() == "":
            continue
        vals[k] = str(to_int_floor(raw, default=mn, min_value=mn))

    # E〜J の 0/1 を丸める（空なら空のまま）
    for k in YN_FIELDS:
        raw = str(vals.get(k, "")).strip()
        if raw == "":
            vals[k] = ""
        else:
            r = raw.translate(FW_TO_HW)
            vals[k] = "1" if r == "1" else "0"

    return vals

# ===============================
# 新フォーマット用パーサー
# ===============================

# 質問文 → キー のマッピング（新フォーマット）
QUESTION_TO_KEY_NEW = {
    "当院を受診頂く理由は何ですか？": "H",
    "今回、困っている症状あるいは相談したい症状は何ですか。": "F",
    "症状はいつからありますか？": "E",
    "症状が出るようになったきっかけは何ですか？": "D",
    "この症状に対して、これまで治療を受けたことがありますか。ある場合はどこでどのような治療を受けましたか。": "G",
    "最終学歴を教えてください。": "A",
    "職歴について教えてください。": "B",
    "現在の家族構成について教えてください。": "C",
    "血縁家族について伺います。精神や神経に関する病気をお持ちの方がいらっしゃいますか。": "X1",
    "あなた自身の既往歴について伺います。体の病気をお持ちですか。": "X2",
    "服用中の薬": "X3",
    "アレルギー": "X4",
    "お酒を飲みますか?": "X5",
    "タバコを吸いますか?": "X6",
    "これまで違法薬物（覚せい剤、大麻など）を使ったことがありますか。": "X7",
    "その他、今回の診察で特に質問したいことや伝えておきたいことはありますか？": "X8",
}

def parse_uploaded_txt_new(text):
    """
    新フォーマット用：
      【質問文】回答
    の1行形式を想定。
    上記 QUESTION_TO_KEY_NEW にある質問だけを拾って A,B,C,D,E,F,G,H,X1〜X8 に入れる。
    """
    vals = {k: "" for k in ALL_KEYS_NEW}
    lines = text.splitlines()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^【(.+?)】(.*)$", line)
        if not m:
            continue
        q = m.group(1).strip()
        ans = m.group(2).strip()
        key = QUESTION_TO_KEY_NEW.get(q)
        if key:
            vals[key] = ans

    return vals

# ===============================
# 旧フォーマット用テキスト生成
# ===============================

def build_text_old(vals):
    # --- 兄弟人数 ---
    if vals.get("B", "1") == "1":
        sibling_text = "出生。同胞なし。"
    else:
        sibling_text = f"同胞{val_or_x(vals.get('B'))}人の第{val_or_x(vals.get('C'))}子として出生。"

    # --- 入院歴 ---
    if vals.get("X5", "0") == "0":
        hospital_text = "入院歴なし。"
    else:
        hospital_text = f"入院歴は{val_or_x(vals.get('X5'))}回ある。"

    # --- 転院回数と転院先(X7) ---
    x6 = (vals.get("X6") or "").strip()
    x7 = val_or_x(vals.get("X7"))  # 未入力なら "X"

    if x6 == "" or x6 == "0":
        transfer_text = f"{hospital_text}その後、転院したことはない。"
    else:
        transfer_text = (
            f"{hospital_text}"
            f"その後、{x6}回転院したことがある（{x7}）。"
        )

    # --- 精神科通院 ---
    if vals.get("X1", "0") == "0":
        psych_text = "精神科への通院歴はこれまでなし。"
    else:
        psych_text = (
            f"精神科への通院は{val_or_x(vals.get('X1'))}歳からで、理由は{val_or_x(vals.get('X2'))}のため。"
            f"{val_or_x(vals.get('X3'))}に受診し、{val_or_x(vals.get('X4'))}と診断された。"
            f"{transfer_text}"
        )

    # --- E〜J 0/1 → あり/なし（未入力なら X） ---
    e_text = yes_no_text(vals.get("E"), "いじめあり", "いじめなし")
    f_text = yes_no_text(vals.get("F"), "不登校あり", "不登校なし")
    g_text = yes_no_text(vals.get("G"), "いじめあり", "いじめなし")
    h_text = yes_no_text(vals.get("H"), "不登校あり", "不登校なし")
    i_text = yes_no_text(vals.get("I"), "いじめあり", "いじめなし")
    j_text = yes_no_text(vals.get("J"), "不登校あり", "不登校なし")

    # --- X8：発症時期 ---
    x8_jp = format_month(vals.get("X8", ""))

    # --- 発症文：X8頃から、X10のきっかけで、X9が出現した。 ---
    onset_text = ""
    if vals.get("X8") or vals.get("X9") or vals.get("X10"):
        onset_text = (
            f"{x8_jp}頃から、"
            f"{val_or_x(vals.get('X10'))}のきっかけで、"
            f"{val_or_x(vals.get('X9'))}が出現した。"
        )

    # --- 全体テキスト ---
    text = (
f"【生活歴】\n"
f"{val_or_x(vals.get('A'))}にて{sibling_text}"
f"発達の遅れや異常については{val_or_x(vals.get('D'))}。 "
f"小学校では{e_text}、{f_text}。 "
f"中学校では{g_text}、{h_text}。 "
f"高校では{i_text}、{j_text}。 "
f"最終学歴は、{val_or_x(vals.get('K'))}。卒業後は{val_or_x(vals.get('L'))}に就職。 "
f"{val_or_x(vals.get('M'))}歳で結婚。子供は{val_or_x(vals.get('N'))}人。離婚は{val_or_x(vals.get('O'))}。 "
f"現在は{val_or_x(vals.get('P'))}と{val_or_x(vals.get('Q'))}にて生活。\n"
f"【現病歴】\n"
f"{psych_text}"
f"{onset_text}\n"
f"【既往歴】{val_or_x(vals.get('T'))}\n"
f"【家族歴】{val_or_x(vals.get('U'))}\n"
f"【喫煙歴】{val_or_x(vals.get('S'))}\n"
f"【飲酒歴】{val_or_x(vals.get('R'))}\n"
    )
    return text

# ===============================
# 新フォーマット用テキスト生成
# ===============================

def build_text_new(vals):
    """
    新フォーマット指定の出力：

    【生活現病歴】
    最終学歴はA。その後、Bで勤める。現在、Cと暮らしている。DのためにEごろから、Fの症状が出始めた。Gなどの治療をした。Hを理由に当院初診。

    【家族歴】X1
    【既往歴】X２
    【服用中の薬】X3
    【アレルギー】X4
    【飲酒歴】X5
    【喫煙歴】X6
    【違法薬物の使用歴】X7
    【備考】X8
    """
    A = val_or_x(vals.get("A"))
    B = val_or_x(vals.get("B"))
    C = val_or_x(vals.get("C"))
    D = val_or_x(vals.get("D"))
    E = val_or_x(vals.get("E"))
    F = val_or_x(vals.get("F"))
    G = val_or_x(vals.get("G"))
    H = val_or_x(vals.get("H"))

    X1 = val_or_x(vals.get("X1"))
    X2 = val_or_x(vals.get("X2"))
    X3 = val_or_x(vals.get("X3"))
    X4 = val_or_x(vals.get("X4"))
    X5 = val_or_x(vals.get("X5"))
    X6 = val_or_x(vals.get("X6"))
    X7 = val_or_x(vals.get("X7"))
    X8 = val_or_x(vals.get("X8"))

    text = (
f"【生活現病歴】\n"
f"最終学歴は{A}。その後、{B}で勤める。現在、{C}と暮らしている。"
f"{D}のために{E}ごろから、{F}の症状が出始めた。"
f"{G}などの治療をした。{H}を理由に当院初診。\n\n"
f"【家族歴】{X1}\n"
f"【既往歴】{X2}\n"
f"【服用中の薬】{X3}\n"
f"【アレルギー】{X4}\n"
f"【飲酒歴】{X5}\n"
f"【喫煙歴】{X6}\n"
f"【違法薬物の使用歴】{X7}\n"
f"【備考】{X8}\n"
    )
    return text

# ===============================
# ルーティング
# ===============================

# 旧フォーマット用アップロード
@app.route("/upload", methods=["GET", "POST"])
def upload_old():
    if request.method == "POST":
        file = request.files.get("txtfile")
        if not file or file.filename == "":
            return render_template_string("<p>ファイルが選択されていません。</p><p><a href='/upload'>戻る</a></p>")
        text = file.read().decode("utf-8", errors="ignore")
        vals = parse_uploaded_txt_old(text)
        # セッションに保存（旧フォーマットは従来どおりキー単位で保存）
        for k, v in vals.items():
            session[k] = v
        session["old_format_loaded"] = True
        return redirect(url_for("output_old"))

    return render_template_string("""
<h2>旧フォーマット（A〜X10）用テキストをアップロード</h2>
<form method="post" enctype="multipart/form-data" style="line-height:1.9%;">
  <input type="file" name="txtfile" accept=".txt" required>
  <button type="submit">送信</button>
</form>
<p style="margin-top:12px;">※ 見出しのラベルは（A）でも (A) でも対応しています。</p>
<p><a href="/">トップに戻る</a></p>
<p><a href="/output">出力ページを見る</a></p>
""")

@app.route("/output")
def output_old():
    if not session.get("old_format_loaded"):
        return render_template_string("""
<p>まだ旧フォーマットのテキストが読み込まれていません。</p>
<p><a href="/upload">旧フォーマットのアップロードページへ</a></p>
<p><a href="/">トップに戻る</a></p>
""")
    vals = {k: session.get(k, "") for k in ALL_KEYS_OLD}
    text = build_text_old(vals)
    return render_template_string("""
<h2>旧フォーマット：自動生成テキスト</h2>
<div style="white-space:pre-wrap; border:1px solid #ccc; padding:12px; border-radius:8px; text-align:left;">
{{- text -}}
</div>
<p style="margin-top:12px;">
  <a href="/upload">旧フォーマットで別ファイル</a> |
  <a href="/download">旧フォーマットテキストを保存</a> |
  <a href="/reset">入力をリセット</a> |
  <a href="/">トップに戻る</a>
</p>
""", text=text)

@app.route("/download")
def download_txt_old():
    if not session.get("old_format_loaded"):
        return redirect(url_for("upload_old"))
    vals = {k: session.get(k, "") for k in ALL_KEYS_OLD}
    text = build_text_old(vals)
    resp = make_response(text)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="seikatsu_genbyoreki_old.txt"'
    return resp

# 新フォーマット用アップロード
@app.route("/upload_new", methods=["GET", "POST"])
def upload_new():
    if request.method == "POST":
        file = request.files.get("txtfile")
        if not file or file.filename == "":
            return render_template_string("<p>ファイルが選択されていません。</p><p><a href='/upload_new'>戻る</a></p>")
        text = file.read().decode("utf-8", errors="ignore")
        vals = parse_uploaded_txt_new(text)
        # セッションに保存（新フォーマットは1つの辞書として保存）
        session["new_vals"] = vals
        session["new_format_loaded"] = True
        return redirect(url_for("output_new"))

    return render_template_string("""
<h2>新フォーマット（日本語問診）用テキストをアップロード</h2>
<form method="post" enctype="multipart/form-data" style="line-height:1.9%;">
  <input type="file" name="txtfile" accept=".txt" required>
  <button type="submit">送信</button>
</form>
<p style="margin-top:12px;">※ 例のように「【質問】回答」という形式のtxtを想定しています。</p>
<p><a href="/">トップに戻る</a></p>
<p><a href="/output_new">出力ページを見る</a></p>
""")

@app.route("/output_new")
def output_new():
    if not session.get("new_format_loaded"):
        return render_template_string("""
<p>まだ新フォーマットのテキストが読み込まれていません。</p>
<p><a href="/upload_new">新フォーマットのアップロードページへ</a></p>
<p><a href="/">トップに戻る</a></p>
""")
    vals = session.get("new_vals", {}) or {}
    text = build_text_new(vals)
    return render_template_string("""
<h2>新フォーマット：自動生成テキスト</h2>
<div style="white-space:pre-wrap; border:1px solid #ccc; padding:12px; border-radius:8px; text-align:left;">
{{- text -}}
</div>
<p style="margin-top:12px;">
  <a href="/upload_new">新フォーマットで別ファイル</a> |
  <a href="/download_new">新フォーマットテキストを保存</a> |
  <a href="/reset_new">入力をリセット</a> |
  <a href="/">トップに戻る</a>
</p>
""", text=text)

@app.route("/download_new")
def download_txt_new():
    if not session.get("new_format_loaded"):
        return redirect(url_for("upload_new"))
    vals = session.get("new_vals", {}) or {}
    text = build_text_new(vals)
    resp = make_response(text)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="seikatsu_genbyoreki_new.txt"'
    return resp

# リセット（両方まとめて消す）
@app.route("/reset")
def reset():
    for k in list(session.keys()):
        session.pop(k, None)
    return redirect(url_for("root"))

@app.route("/reset_new")
def reset_new():
    # 新フォーマット関連だけ消す
    for k in ["new_vals", "new_format_loaded"]:
        session.pop(k, None)
    return redirect(url_for("upload_new"))

# トップページ：両方へのリンクを表示
@app.route("/")
def root():
    return render_template_string("""
<h2>問診テキスト → 自動文章生成ツール</h2>
<ul>
  <li><a href="/upload">旧フォーマット（A〜X10）用アップロード</a></li>
  <li><a href="/upload_new">新フォーマット（日本語問診）用アップロード</a></li>
</ul>
""")

if __name__ == "__main__":
    app.run(debug=True)
