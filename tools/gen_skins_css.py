"""web/skins.css üretici — görünüm paketlerinin renk/yazı/yerleşim kuralları.

Çalıştır: python tools/gen_skins_css.py
"""
from pathlib import Path

SYS = 'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif'
MONO = 'ui-monospace,Consolas,monospace'

# id: (açık jetonlar, koyu jetonlar | None, ek CSS)
SK = {}


def tok(d):
    return ";".join(f"--{k}:{v}" for k, v in d.items())


SK["defter"] = (
    dict(bg="#f3f1ec", card="#f3f1ec", ink="#1a1a1a", muted="#5c5a55", line="#cfccc4", pri="#b4410c", **{"pri-d": "#8f330a"},
         side="#f3f1ec", **{"side-ink": "#1a1a1a"}, r="0px", font=f"'IBM Plex Sans',{SYS}", **{"font-h": "'IBM Plex Sans'", "font-n": f"'IBM Plex Mono',{MONO}"}),
    dict(bg="#16150f", card="#16150f", ink="#ece8de", muted="#a39e92", line="#3a372e", pri="#f07b3f", **{"pri-d": "#d9652a"}, side="#16150f", **{"side-ink": "#ece8de"}),
    """
.card{border:0;border-top:1px solid var(--ink);background:transparent;padding:16px 0}
.side{border-bottom:1px solid var(--ink)}.nav a.on{background:none;color:var(--ink);box-shadow:inset 0 -3px var(--pri)}
.stat .i{display:none}.stat .n{font-weight:500}th{border-bottom:1px solid var(--ink)}
""")

SK["kayit"] = (
    dict(bg="#fbfaf7", card="#fbfaf7", ink="#22262a", muted="#6b6f73", line="#e3e0d8", pri="#1e4d3a", **{"pri-d": "#123326"},
         side="#fbfaf7", **{"side-ink": "#22262a"}, r="4px", font=f"'Source Sans 3',{SYS}", **{"font-h": "'Source Serif 4',Georgia,serif", "font-n": "'Source Serif 4',Georgia,serif"}),
    dict(bg="#141714", card="#141714", ink="#e6e8e3", muted="#9ea39b", line="#2c312c", pri="#6fb894", **{"pri-d": "#57a07c"}, side="#141714", **{"side-ink": "#e6e8e3"}),
    """
.side{border-right:1px solid var(--line)}.brand{color:var(--pri)}.brand b{color:inherit}
.nav a.on{background:color-mix(in srgb,var(--pri) 12%,transparent);color:var(--pri)}.nav a:hover{background:color-mix(in srgb,var(--ink) 5%,transparent)}
.card{border:0;border-top:1px solid var(--line);background:transparent;padding:18px 0}
h1{font-size:34px;font-weight:600;border-bottom:1px solid var(--ink);padding-bottom:12px}
.stat .i{display:none}.stat .n{font-size:44px;font-weight:400}
""")

SK["kontrol"] = (
    dict(bg="#121417", card="#1a1d21", ink="#e4e7ec", muted="#8b929c", line="#2c3036", pri="#e8a33d", **{"pri-d": "#d18d27"},
         side="#0b0c0e", **{"side-ink": "#c9ced6"}, r="0px", font=f"Barlow,{SYS}", **{"font-h": "'Barlow Condensed',Barlow,sans-serif", "font-n": f"'JetBrains Mono',{MONO}"}),
    None,
    """
.card{border:0;border-top:2px solid #3b4048}h1,h2{text-transform:uppercase;letter-spacing:.05em}
.btn.p{color:#121417}.nav a.on{background:#1d2025;color:var(--pri)}
""")

SK["arama"] = (
    dict(bg="#ffffff", card="#ffffff", ink="#111111", muted="#6a6a6a", line="#ececec", pri="#e0452b", **{"pri-d": "#c13820"},
         side="#ffffff", **{"side-ink": "#555555"}, r="14px", font=f"Manrope,{SYS}", **{"font-h": "Manrope", "font-n": f"'JetBrains Mono',{MONO}"}),
    dict(bg="#0f0f10", card="#0f0f10", ink="#f2f2f2", muted="#9a9a9a", line="#262628", pri="#ff6a4d", **{"pri-d": "#e85538"}, side="#0f0f10", **{"side-ink": "#a8a8a8"}),
    """
.card{border:1px solid var(--line);box-shadow:none}.nav a.on{background:none;color:var(--ink);font-weight:700}
.btn{border-radius:999px}.stat .i{display:none}h1{font-weight:700;letter-spacing:-.02em}
""")

SK["blok"] = (
    dict(bg="#ecebe6", card="#ffffff", ink="#111111", muted="#55554f", line="#111111", pri="#f2c230", **{"pri-d": "#dcae1e"},
         side="#ecebe6", **{"side-ink": "#111111"}, r="0px", font=f"Archivo,{SYS}", **{"font-h": "Archivo", "font-n": "Archivo"}),
    dict(bg="#121212", card="#1c1c1c", ink="#f1f0ea", muted="#a8a7a0", line="#f1f0ea", pri="#f2c230", **{"pri-d": "#dcae1e"}, side="#121212", **{"side-ink": "#f1f0ea"}),
    """
.card{border:0}h1{font-size:44px;font-weight:800;letter-spacing:-.03em}h2{font-weight:800;font-size:22px;border-bottom:3px solid var(--ink);padding-bottom:8px}
.btn.p{color:#111}.nav a{font-family:'Archivo Narrow',Archivo,sans-serif;text-transform:uppercase;font-weight:700}
.nav a.on{background:none;color:var(--ink);box-shadow:inset 0 -3px var(--ink)}th{border-bottom:3px solid var(--ink)}td{border-bottom-color:var(--ink)}
.stat .i{display:none}.stat .n{font-size:64px;font-weight:800;letter-spacing:-.04em;line-height:1}
.g4>.card:nth-child(4n+1){background:#111;color:#ecebe6}.g4>.card:nth-child(4n+1) .l{color:#bdbdb6}
.g4>.card:nth-child(4n+2){background:var(--pri);color:#111}.g4>.card:nth-child(4n+2) .l{color:#111}
.g4>.card:nth-child(4n+3){background:#2347c5;color:#fff}.g4>.card:nth-child(4n+3) .l{color:#dfe5ff}
""")

SK["masaustu"] = (
    dict(bg="#e9e9e7", card="#ffffff", ink="#1d1d1d", muted="#5c5c58", line="#cfcfcc", pri="#2b5f9e", **{"pri-d": "#214b7e"},
         side="#f6f6f5", **{"side-ink": "#1d1d1d"}, r="2px", font=f"'Noto Sans',{SYS}", **{"font-h": "'Noto Sans'", "font-n": f"'Noto Sans',{MONO}"}),
    dict(bg="#1f1f1f", card="#2a2a2a", ink="#e8e8e8", muted="#a8a8a8", line="#3c3c3c", pri="#5d9be0", **{"pri-d": "#4a86cc"}, side="#252525", **{"side-ink": "#e8e8e8"}),
    """
body{font-size:13px}.card{box-shadow:none;padding:12px}h1{font-size:18px}.stat .i{display:none}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--ink) 3%,transparent)}th{background:color-mix(in srgb,var(--ink) 4%,transparent);border-right:1px solid var(--line)}
td,th{padding:6px 10px}.btn{padding:6px 12px;font-weight:500}
""")

SK["bina"] = (
    dict(bg="#0f2f52", card="rgba(15,47,82,.88)", ink="#eaf2ff", muted="#9fb8d6", line="rgba(234,242,255,.28)", pri="#ffb547", **{"pri-d": "#f0a12e"},
         side="#0c2744", **{"side-ink": "#d6e4f7"}, r="0px", font=f"'Chakra Petch',{SYS}", **{"font-h": "'Chakra Petch'", "font-n": f"'Share Tech Mono',{MONO}"}),
    None,
    """
body{background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:24px 24px;background-attachment:fixed}
.card{border:1px solid rgba(234,242,255,.45)}h1,h2{text-transform:uppercase;letter-spacing:.04em}.btn.p{color:#0f2f52}
.nav a.on{background:none;color:var(--pri);outline:2px solid var(--pri);outline-offset:-2px}
""")

SK["gazete"] = (
    dict(bg="#f2ecdc", card="#f2ecdc", ink="#1b1a17", muted="#5a554a", line="#1b1a17", pri="#9b2a17", **{"pri-d": "#7a1f10"},
         side="#f2ecdc", **{"side-ink": "#1b1a17"}, r="0px", font="'Libre Baskerville',Georgia,serif", **{"font-h": "'Playfair Display',Georgia,serif", "font-n": "'Playfair Display',Georgia,serif"}),
    dict(bg="#191712", card="#191712", ink="#ebe4d2", muted="#a69f8d", line="#ebe4d2", pri="#e0714f", **{"pri-d": "#c95b3a"}, side="#191712", **{"side-ink": "#ebe4d2"}),
    """
body{font-size:13.5px}.card{border:0;border-top:3px double var(--ink);background:transparent;padding:14px 0}
h1{font-weight:900;font-size:40px}h2{font-weight:900;font-size:22px}.brand{font-family:UnifrakturCook,serif;font-size:30px;color:var(--ink)}.brand b{color:inherit}.brand img{display:none}
.nav a{text-transform:uppercase;letter-spacing:.12em;font-size:11px}.nav a.on{background:none;color:var(--pri);text-decoration:underline}
.side{border-bottom:3px double var(--ink)}.stat .i{display:none}.stat .n{font-weight:900;font-size:40px}.btn{border-color:var(--ink)}
""")

SK["terminal"] = (
    dict(bg="#050b07", card="transparent", ink="#7dffa1", muted="#4fbf73", line="#1f5a33", pri="#7dffa1", **{"pri-d": "#b5ffc9"},
         side="#050b07", **{"side-ink": "#7dffa1"}, r="0px", font="VT323,monospace", **{"font-h": "VT323,monospace", "font-n": "VT323,monospace"}),
    None,
    """
body{font-size:20px;line-height:1.2;text-shadow:0 0 6px rgba(125,255,161,.45);background-image:repeating-linear-gradient(0deg,rgba(0,0,0,.35) 0 1px,transparent 1px 3px)}
.card{border:4px double var(--ink)}h1,h2,th{text-transform:uppercase}input,select,textarea{background:transparent;border-color:var(--line)}
.btn{background:transparent;border-color:var(--ink);text-shadow:inherit}.btn.p,.nav a.on{background:var(--ink);color:#050b07;text-shadow:none}
.pill{border-radius:0}.avatar{border-radius:0;color:#050b07}.stat .i{display:none}.small{font-size:16px}
""")

SK["sohbet"] = (
    dict(bg="#e7e4ee", card="#ffffff", ink="#1c1830", muted="#5b5670", line="#cfcadb", pri="#5a3fd6", **{"pri-d": "#4630b8"},
         side="#1c1830", **{"side-ink": "#e7e4ee"}, r="14px", font=f"'DM Sans',{SYS}", **{"font-h": "'DM Sans'", "font-n": f"'DM Sans',{SYS}"}),
    dict(bg="#14121c", card="#1f1c2b", ink="#ebe8f5", muted="#a29dba", line="#332f45", pri="#8b74ff", **{"pri-d": "#7560f0"}, side="#0d0b14", **{"side-ink": "#e7e4ee"}),
    """
.card{border:0;border-radius:4px 16px 16px 16px}.nav .ic{display:none}.nav a::before{content:"#";opacity:.6}
.nav a.on{background:rgba(255,255,255,.12);color:#fff}.stat .i{border-radius:12px}
""")

SK["metro"] = (
    dict(bg="#f7f7f2", card="#ffffff", ink="#16181d", muted="#50545c", line="#e2e2da", pri="#e0402e", **{"pri-d": "#c4321f"},
         side="#f7f7f2", **{"side-ink": "#16181d"}, r="18px", font=f"'Red Hat Display',{SYS}", **{"font-h": "'Red Hat Display'", "font-n": "'Red Hat Display'"}),
    dict(bg="#121317", card="#1b1d23", ink="#f0f0ea", muted="#a2a6ae", line="#2b2e36", pri="#ff6250", **{"pri-d": "#e84c3a"}, side="#121317", **{"side-ink": "#f0f0ea"}),
    """
h1{font-weight:900;letter-spacing:-.02em;font-size:32px}.btn{border-radius:999px;border-width:2px;border-color:var(--ink)}
.nav a{border:2px solid var(--ink);border-radius:999px;font-weight:700}.nav a.on{background:var(--ink);color:var(--bg)}
.stat .i{border-radius:50%;border:5px solid var(--ink);background:var(--card)!important;color:var(--ink)!important}.stat .n{font-weight:900}
""")

SK["mantar"] = (
    dict(bg="#b8875a", card="#fffdf6", ink="#2a1d10", muted="#6a5a48", line="#d8cbb4", pri="#c0392b", **{"pri-d": "#a32d21"},
         side="transparent", **{"side-ink": "#2a1d10"}, r="0px", font="'Courier Prime',Courier,monospace", **{"font-h": "Caveat,cursive", "font-n": "Caveat,cursive"}),
    None,
    """
body{background-image:radial-gradient(rgba(70,40,15,.35) 1px,transparent 1.6px),radial-gradient(rgba(255,230,190,.25) 1px,transparent 1.4px);background-size:7px 7px,11px 11px;background-attachment:fixed}
.shell{border:16px solid #6b4423}h1{font-size:46px;color:#fffdf6;text-shadow:0 2px 3px rgba(0,0,0,.4)}h2{font-size:30px}
.card{border:0;box-shadow:0 8px 16px rgba(0,0,0,.3);position:relative}
.card:not(form)::before{content:"";position:absolute;left:50%;top:-7px;width:15px;height:15px;border-radius:50%;background:var(--pri);box-shadow:0 3px 4px rgba(0,0,0,.4)}
.grid>.card:nth-child(odd){transform:rotate(-.6deg)}.grid>.card:nth-child(even){transform:rotate(.5deg)}
.nav a{background:#f4e3a1;color:#2a1d10;box-shadow:0 4px 8px rgba(0,0,0,.25);border-radius:0;font-weight:700}.nav a:nth-child(3n){background:#cfe6f2}.nav a:nth-child(3n+1){background:#e8e1d3}
.nav a.on{background:var(--pri);color:#fff}.brand{color:#fffdf6;font-family:Caveat,cursive;font-size:34px;text-shadow:0 2px 3px rgba(0,0,0,.4)}.brand b{color:inherit}
.top .who{color:#fffdf6}.top .who .muted{color:#f1e3cd}.stat .i{display:none}.stat .n{font-size:46px}
""")

SK["monitor"] = (
    dict(bg="#000000", card="#000000", ink="#cfd6df", muted="#8a95a3", line="#1f2933", pri="#3cff7a", **{"pri-d": "#2ee66a"},
         side="#05080b", **{"side-ink": "#cfd6df"}, r="0px", font=f"Rajdhani,{SYS}", **{"font-h": "Rajdhani", "font-n": "Rajdhani"}),
    None,
    """
body{font-size:15px}.card{border:1px solid var(--line)}h1,h2{text-transform:uppercase;letter-spacing:.06em}.btn{background:#0c1116;border-color:#3a4652}
.btn.p{color:#000}.stat .n{font-size:52px;font-weight:700;line-height:1}.stat .i{display:none}
.g4>.card:nth-child(5n+1) .n{color:#3cff7a}.g4>.card:nth-child(5n+2) .n{color:#3fd8ff}.g4>.card:nth-child(5n+3) .n{color:#ffd23f}.g4>.card:nth-child(5n+4) .n{color:#ff3b3b}.g4>.card:nth-child(5n) .n{color:#e07bff}
""")

SK["radar"] = (
    dict(bg="#03140f", card="rgba(3,20,15,.92)", ink="#7dfcd2", muted="#3fae8c", line="#16523f", pri="#7dfcd2", **{"pri-d": "#b4ffe6"},
         side="#020e0a", **{"side-ink": "#7dfcd2"}, r="0px", font=f"Oxanium,{SYS}", **{"font-h": "Oxanium", "font-n": "Oxanium"}),
    None,
    """
.card{border:1px solid #1d6b55}h1,h2{text-transform:uppercase;letter-spacing:.08em}.btn{background:transparent;border-color:#1d6b55}
.btn.p{color:#03140f}.nav a.on{background:none;color:#d8fff1;box-shadow:inset 3px 0 var(--pri)}.stat .i{display:none}
""")

DARK_NATIVE = [k for k, v in SK.items() if v[1] is None]

LAYOUT = """
/* ---- yerleşimler ---- */
:root[data-skin] body{font-family:var(--font)}
:root[data-skin] h1,:root[data-skin] h2{font-family:var(--font-h,inherit)}
:root[data-skin] .stat .n,:root[data-skin] .mono{font-family:var(--font-n,inherit)}
:root[data-skin] .card,:root[data-skin] .btn,:root[data-skin] input,:root[data-skin] select,:root[data-skin] textarea{border-radius:var(--r)}
:root[data-skin] .brand{color:var(--side-ink)}:root[data-skin] .brand b{color:var(--pri)}
:root[data-dark] .pill{background:transparent!important;border:1px solid currentColor}
:root[data-dark] .pill.aktif,:root[data-dark] .pill.ok,:root[data-dark] .pill.t-çözüldü{color:#5fe39a}
:root[data-dark] .pill.arızalı,:root[data-dark] .pill.t-yeni,:root[data-dark] .pill.p-acil{color:#ff7a7a}
:root[data-dark] .lbl-prev,:root[data-dark] canvas.sig{background:#fff}

/* üst menü */
:root[data-layout=top] .shell,:root[data-layout=fkeys] .shell{grid-template-columns:1fr;background:none}
:root[data-layout=top] .side,:root[data-layout=fkeys] .side{position:sticky;top:0;z-index:15;height:auto;display:flex;align-items:center;gap:18px;padding:8px 26px;overflow:visible}
:root[data-layout=top] .brand,:root[data-layout=fkeys] .brand{padding:0;font-size:18px;white-space:nowrap}
:root[data-layout=top] .nav,:root[data-layout=fkeys] .nav{flex-direction:row;flex-wrap:wrap;gap:2px 4px}
:root[data-layout=top] .nav a,:root[data-layout=fkeys] .nav a{padding:6px 10px;margin:0;font-size:13px}
:root[data-layout=top] .nav .ic,:root[data-layout=fkeys] .nav .ic{display:none}
:root[data-layout=top] .nav-h,:root[data-layout=fkeys] .nav-h{display:none}
:root[data-layout=top] .side .foot,:root[data-layout=fkeys] .side .foot{display:none}

/* simge şeridi */
:root[data-layout=rail] .shell{grid-template-columns:72px 1fr;background:linear-gradient(to right,var(--side) 72px,var(--bg) 72px)}
:root[data-layout=rail] .side{width:72px;padding:14px 10px;overflow:hidden;transition:width .15s;z-index:25}
:root[data-layout=rail] .side:hover{width:240px;overflow:auto;box-shadow:8px 0 30px rgba(0,0,0,.4)}
:root[data-layout=rail] .brand span,:root[data-layout=rail] .side .foot{display:none}
:root[data-layout=rail] .side:hover .brand span{display:inline}
:root[data-layout=rail] .nav a{white-space:nowrap;padding:12px 15px;font-size:0;gap:0}:root[data-layout=rail] .side:hover .nav a{font-size:inherit;gap:10px}:root[data-layout=rail] .nav a .bdg{display:none}:root[data-layout=rail] .side:hover .nav a .bdg:not([hidden]){display:inline}:root[data-layout=rail] .nav .ic{font-size:17px;flex:0 0 22px}
:root[data-layout=rail] .nav-h{white-space:nowrap;overflow:hidden;height:1px;padding:0;margin:8px 4px;background:var(--line);font-size:0}
:root[data-layout=rail] .side:hover .nav-h{height:auto;background:none;font-size:11px;padding:14px 12px 4px;margin:0}

/* ağaç (klasik masaüstü) */
:root[data-layout=tree] .shell{grid-template-columns:250px 1fr;background:linear-gradient(to right,var(--side) 250px,var(--bg) 250px)}
:root[data-layout=tree] .side{border-right:1px solid var(--line);padding:10px 0}
:root[data-layout=tree] .brand{font-size:15px;padding:4px 14px 10px;color:var(--ink)}:root[data-layout=tree] .brand b{color:var(--pri)}
:root[data-layout=tree] .nav a{border-radius:0;padding:3px 14px 3px 30px;margin:0;border-left:3px solid transparent}
:root[data-layout=tree] .nav a.on{background:var(--card);color:var(--ink);border-left-color:var(--pri);font-weight:600}
:root[data-layout=tree] .nav-h{text-transform:none;letter-spacing:0;font-size:13px;opacity:1;font-weight:600;padding:8px 14px 2px}
:root[data-layout=tree] .nav-h::before{content:"▾ "}:root[data-layout=tree] .main{padding-bottom:40px}
#sbar{position:fixed;left:0;right:0;bottom:0;height:26px;display:flex;gap:24px;align-items:center;padding:0 12px;background:var(--side);border-top:1px solid var(--line);font-size:12px;color:var(--muted);z-index:30}

/* F tuşları */
#fbar{position:fixed;left:0;right:0;bottom:0;display:flex;flex-wrap:wrap;gap:4px 14px;padding:6px 26px;background:var(--bg);border-top:1px solid var(--line);z-index:30}
#fbar button{border:0;background:none;color:var(--ink);font:inherit;cursor:pointer;padding:0;text-shadow:inherit}
#fbar b{background:var(--ink);color:var(--bg);padding:0 5px;margin-right:4px;font-weight:400;text-shadow:none}
:root[data-layout=fkeys] .main{padding-bottom:60px}
:root[data-skin] .faq details{border-color:var(--line)}

/* paket seçici */
.skins{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:8px}
.skins label{cursor:pointer;display:block}.skins input{position:absolute;opacity:0;pointer-events:none}
.skins .sw{display:block;border:2px solid var(--line);border-radius:10px;overflow:hidden;font-family:system-ui,sans-serif;text-shadow:none}
.skins input:checked+.sw{border-color:var(--pri);box-shadow:0 0 0 2px var(--pri)}.skins input:focus-visible+.sw{outline:2px solid var(--pri);outline-offset:2px}
.skins .pv{display:flex;height:54px}.skins .pv i{flex:1}.skins .nm{display:block;padding:6px 8px 7px;font-size:12.5px;font-weight:600;color:var(--ink);background:var(--card);line-height:1.25}
.skins .nm small{display:block;font-weight:400;color:var(--muted);font-size:11px}

/* özel pano yardımcıları */
.sk-dash{min-height:calc(100vh - 110px)}
.sk-btn{font:inherit;cursor:pointer}
"""


def build():
    out = ["/* Üretildi: tools/gen_skins_css.py — elle düzenlemeyin */", LAYOUT]
    for k, (light, dark, extra) in SK.items():
        out.append(f":root[data-skin={k}]{{{tok(light)}}}")
        if dark:
            out.append(f":root[data-skin={k}][data-mode=dark]{{{tok(dark)};color-scheme:dark}}")
        if k in DARK_NATIVE:
            out.append(f":root[data-skin={k}]{{color-scheme:dark}}")
        for line in extra.strip().splitlines():
            # her kuralın seçicilerini paket kapsamına al
            rules = line.split("}")
            for r in rules:
                if "{" not in r:
                    continue
                sel, body = r.split("{", 1)
                sels = ",".join(f":root[data-skin={k}] {s.strip()}" if s.strip() not in ("body",) else f":root[data-skin={k}] body" for s in sel.split(","))
                out.append(f"{sels}{{{body}}}")
    # kullanıcı vurgu seçimi her paketin üstüne yazılır
    acc = {"blue": ("#1463ff", "#0b4fe0"), "green": ("#0f8f55", "#0b7243"), "teal": ("#0e8a8a", "#0a6d6d"), "purple": ("#6d4ae0", "#5636c4"),
           "orange": ("#d9640f", "#b5510a"), "red": ("#c7333b", "#a3262d"), "slate": ("#3d4f6e", "#2c3a52")}
    for a, (p, d) in acc.items():
        out.append(f":root[data-skin][data-accent={a}],:root[data-skin][data-accent={a}][data-mode=dark]{{--pri:{p};--pri-d:{d}}}")
    Path(__file__).resolve().parent.parent.joinpath("web", "skins.css").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
