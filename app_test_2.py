from flask import Flask, request, redirect, url_for, render_template_string, session, make_response

app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret"

FIELDS = [
    ("A", "出生地（A）"),
    ("B", "あなたを含めての兄弟の人数（B）"),
    ("C", "あなたの順番（C）"),
    ("D", "発歴の遅れなどの指摘（D）"),
    ("E", "小学校でのいじめ（E） 0=なし / 1=あり"),
    ("F", "小学校での不登校（F） 0=なし / 1=あり"),
    ("G", "中学校でのいじめ（G） 0=なし / 1=あり"),
    ("H", "中学校での不登校（H） 0=なし / 1=あり"),
    ("I", "高校でのいじめ（I） 0=なし / 1=あり"),
    ("J", "高校での不登校（J） 0=なし / 1=あり"),
    ("K", "最終学歴（K）"),
    ("L", "K卒業後の就職先（L）"),
    ("M", "結婚年齢（M）"),
    ("N", "子供の人数（N）"),
    ("O", "離婚（O）"),
    ("P", "現在の同居人（P）"),
    ("Q", "現在の住所：都道府県（Q）"),
    ("R", "飲酒歴（R）"),
    ("S", "喫煙歴（S）"),
    ("T", "既往歴（T）"),
    ("U", "家族歴（U）"),
    ("X1", "精神科通院開始年齢（X1）"),
    ("X2", "初回通院の理由（X2）"),
    ("X3", "初回受診病院またはクリニック名（X3）"),
    ("X4", "初回診断名（X4）"),
    ("X5", "入院回数（X5）"),
    ("X6", "転院回数（X6）"),
    ("X7", "今回の辛さの始まり（X7）"),  # YYYY-MM
    ("X8", "今回の症状（X8）"),
    ("X9", "今回の症状のきっかけ（X9）"),
]

NUMBER_MIN = {
    "B": 0, "C": 1, "M": 0, "N": 0,
    "X1": 0, "X5": 0, "X6": 0,
    "E": 0, "F": 0, "G": 0, "H": 0, "I": 0, "J": 0
}


def yes_no_text(v, yes="あり", no="なし"):
    return yes if v == "1" else no


def format_month(ym_str):
    """'YYYY-MM' → 'YYYY年M月' に変換"""
    try:
        year, month = ym_str.split("-")
        return f"{int(year)}年{int(month)}月"
    except Exception:
        return ym_str  # 入力が空や不正ならそのまま返す


def build_text():
    vals = {k: session.get(k, "").strip() for k, _ in FIELDS}

    # --- 兄弟人数 ---
    if vals.get("B", "") == "1":
        sibling_text = "同胞なし。"
    else:
        sibling_text = f"同胞{vals['B']}人の第{vals['C']}子として出生。"

    # --- 入院歴 ---
    if vals.get("X5", "") == "0":
        hospital_text = "入院歴なし。"
    else:
        hospital_text = f"入院歴は{vals['X5']}回ある。"

    # --- 転院回数 ---
    if vals.get("X6", "") == "0":
        transfer_text = f"{hospital_text}その後、転院したことはない。"
    else:
        transfer_text = f"{hospital_text}その後、{vals['X6']}回転院したことがある。"

    # --- 精神科通院有無 ---
    if vals.get("X1", "") == "0":
        psych_text = "精神科への通院歴はこれまでなし。"
    else:
        psych_text = (
            f"精神科への通院は{vals['X1']}歳からで、理由は{vals['X2']}のため。"
            f"{vals['X3']}に受診し、{vals['X4']}と診断された。"
            f"{transfer_text}"
        )

    # --- E〜J 0/1をあり/なしに変換 ---
    e_text = yes_no_text(vals["E"], "いじめあり", "いじめなし")
    f_text = yes_no_text(vals["F"], "不登校あり", "不登校なし")
    g_text = yes_no_text(vals["G"], "いじめあり", "いじめなし")
    h_text = yes_no_text(vals["H"], "不登校あり", "不登校なし")
    i_text = yes_no_text(vals["I"], "いじめあり", "いじめなし")
    j_text = yes_no_text(vals["J"], "不登校あり", "不登校なし")

    # --- X7 (年月) を日本語形式に ---
    x7_jp = format_month(vals["X7"])

    # --- 「X7頃から、X9のきっかけで、X8が出現した。」 ---
    onset_text = f"{x7_jp}頃から、{vals['X9']}のきっかけで、{vals['X8']}が出現した。"

    # --- 全体文 ---
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


@app.route("/input", methods=["GET", "POST"])
def input_page():
    if request.method == "POST":
        for key, _ in FIELDS:
            val = request.form.get(key, "").strip()
            if key in NUMBER_MIN and val != "":
                try:
                    n = int(val)
                except ValueError:
                    n = NUMBER_MIN[key]
                if n < NUMBER_MIN[key]:
                    n = NUMBER_MIN[key]
                val = str(n)
            session[key] = val
        return redirect(url_for("output_page"))

    placeholders = {
        "A":"東京", "B":"0", "C":"1", "D":"特記事項なし",
        "E":"0", "F":"0", "G":"0", "H":"0", "I":"0", "J":"0",
        "K":"大学", "L":"企業勤務", "M":"28", "N":"0", "O":"なし",
        "P":"配偶者", "Q":"東京都", "R":"たまに", "S":"なし",
        "T":"高血圧", "U":"母がうつ病",
        "X1":"25", "X2":"不眠", "X3":"○○病院", "X4":"うつ病",
        "X5":"0", "X6":"0",
        "X7":"2025-05", "X8":"不眠・意欲低下", "X9":"仕事のストレス"
    }

    form_html = """
<h2>生活歴・現病歴 入力フォーム</h2>
<form method="post" style="max-width:720px; line-height:1.9;">
"""
    for key, label in FIELDS:
        if key == "X7":
            current = session.get(key, "")
            ph = placeholders.get(key, "")
            form_html += f"""
<label>{label}</label><br>
<input type="month" name="{key}" value="{current}" placeholder="{ph}" style="width:100%;" required>
<br>
"""
            continue

        t = "number" if key in NUMBER_MIN else "text"
        min_attr = f'min="{NUMBER_MIN[key]}"' if key in NUMBER_MIN else ""
        current = session.get(key, "")
        ph = placeholders.get(key, "")
        form_html += f"""
<label>{label}</label><br>
<input type="{t}" name="{key}" {min_attr} value="{current}" placeholder="{ph}" style="width:100%;" required>
<br>
"""
    form_html += """
<button type="submit" style="margin-top:12px;">送信</button>
</form>
<p style="margin-top:16px;">
  <a href="/output">出力ページを見る</a> |
  <a href="/download">テキストを保存</a> |
  <a href="/reset">入力をリセット</a>
</p>
"""
    return render_template_string(form_html)


@app.route("/output")
def output_page():
    missing = [k for k, _ in FIELDS if session.get(k, "") == ""]
    if missing:
        return render_template_string("""
<p>未入力の項目があります（{{ missing }}）。</p>
<p><a href="/input">入力ページへ戻る</a></p>
""", missing=",".join(missing))

    text = build_text()
    return render_template_string("""
<h2>自動生成テキスト</h2>
<div style="white-space:pre-wrap; border:1px solid #ccc; padding:12px; border-radius:8px; text-align:left;">
{{- text -}}
</div>
<p style="margin-top:12px;">
  <a href="/input">入力を修正する</a> |
  <a href="/download">テキストを保存</a> |
  <a href="/reset">入力をリセット</a>
</p>
""", text=text)


@app.route("/download")
def download_txt():
    text = build_text()
    resp = make_response(text)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="seikatsu_genbyoreki.txt"'
    return resp


@app.route("/reset")
def reset():
    for k, _ in FIELDS:
        session.pop(k, None)
    return redirect(url_for("input_page"))


if __name__ == "__main__":
    app.run(debug=True)
