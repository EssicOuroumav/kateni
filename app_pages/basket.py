import pandas as pd
import streamlit as st

from kateni.affichage import barre_chances
from kateni.basket import PERIODES, fr, libelle, marches
from kateni.ui import basket_a_venir, choisir_jour, jour_choisi, modele_basket

DRAPEAUX_BASKET = {"NBA": "🇺🇸", "EuroLeague": "🇪🇺", "EuroCup": "🇪🇺"}
st.caption("Pronostics de basket : NBA, EuroLeague et EuroCup. Heures d'Abidjan. Le modèle est vérifié sur la "
           "saison 2025-26 (voir « Comment lire ces chances ? » en bas).")

modeles = {p: modele_basket(p) for p in PERIODES}
m = modeles["Match"]
if m is None:
    st.info("Données de basket indisponibles pour l'instant.", icon=":material/sports_basketball:")
    st.stop()


def tous_les_marches(dom: str, ext: str, ligue: str) -> dict:
    out = {}
    for periode, mod in modeles.items():
        if mod is None:
            continue
        a, b = mod.points(dom, ext, ligue)
        out.update(marches(a, b, mod.sd_ecart, mod.sd_total, periode))
    return out


def carte(r: dict) -> None:
    dom, ext, ligue = r["HomeTeam"], r["AwayTeam"], r["ligue"]
    with st.container(border=True):
        heure = pd.Timestamp(r["DateUtc"]).strftime("%H:%M")
        st.markdown(f"**{dom} – {ext}** :gray-badge[:material/schedule: {heure}]")
        if not (m.connait(dom) and m.connait(ext)):
            st.caption("Une des deux équipes est trop peu connue (moins de 5 matchs) : pas de pronostic.")
            return
        a, b = m.points(dom, ext, ligue)
        p = tous_les_marches(dom, ext, ligue)
        v = p["Vainqueur"]
        fav, q = (dom, v["1"]) if v["1"] >= v["2"] else (ext, v["2"])
        couleur = "green" if q >= 0.7 else "blue" if q >= 0.55 else "orange"
        st.markdown(f":{couleur}-badge[{fav} gagne {q:.0%}] · score attendu **{round(a)} – {round(b)}** · "
                    f"total {fr(a + b)} points · écart {fr(abs(a - b))}")
        st.html(barre_chances(dom, ext, (v["1"], 0.0, v["2"])))
        with st.expander("Toutes les prédictions"):
            lignes = [{"Prédiction": libelle(mk, s, dom, ext), "Chance": c, "Cote juste": 1 / c if c > 0.005 else None}
                      for mk, d in p.items() for s, c in d.items() if mk != "Total pair ou impair"]
            lignes += [{"Prédiction": "Total de points pair (ou impair)", "Chance": 0.5, "Cote juste": 2.0}]
            df = pd.DataFrame(lignes).sort_values("Chance", ascending=False, kind="mergesort")
            st.dataframe(df, hide_index=True, height=320, column_config={
                "Chance": st.column_config.ProgressColumn("Chance", format="percent", min_value=0, max_value=1),
                "Cote juste": st.column_config.NumberColumn("Cote juste", format="%.2f",
                                                            help="1 ÷ chance : Betclic doit payer plus pour que le pari vaille le coup.")})


# ---------------------------------------------------------------- matchs à venir
cal = basket_a_venir()
ligues = [l for l in ("NBA", "EuroLeague", "EuroCup") if l in set(cal["ligue"])] if len(cal) else []
if not ligues:
    st.info("Aucun match de basket à venir dans les prochains jours.", icon=":material/event_busy:")
else:
    ligue = st.segmented_control("Ligue", ligues, default=ligues[0], required=True, key="bk_ligue",
                                 format_func=lambda l: f"{DRAPEAUX_BASKET[l]} {l}")
    d = cal[cal["ligue"] == ligue].copy()
    d["jour"] = pd.to_datetime(d["DateUtc"], utc=True).dt.date
    tous = sorted(d["jour"].unique())
    # On part du jour choisi dans le Calendrier (ou du premier jour de match qui suit)
    debut = next((i for i, j in enumerate(tous) if j >= jour_choisi()), max(len(tous) - 7, 0))
    jours = tous[debut:debut + 7]
    jour = st.segmented_control("Jour", jours, default=jours[0], required=True, key=f"bk_jour_{ligue}",
                                format_func=lambda j: f"{j:%d/%m}")
    for _, r in d[d["jour"] == jour].iterrows():
        carte(r)

# ---------------------------------------------------------------- simulation libre
with st.expander("Simuler n'importe quel match", icon=":material/tune:"):
    equipes = sorted(m.attaque, key=str.lower)
    c = st.columns(2)
    dom = c[0].selectbox("Équipe à domicile", equipes, index=None, placeholder="Choisis", key="bk_dom")
    ext = c[1].selectbox("Équipe à l'extérieur", equipes, index=None, placeholder="Choisis", key="bk_ext")
    if dom and ext and dom != ext:
        carte({"HomeTeam": dom, "AwayTeam": ext, "ligue": m.ligue_equipe.get(dom),
               "DateUtc": pd.Timestamp.now(tz="UTC")})

with st.expander("Comment lire ces chances ?", icon=":material/help:"):
    st.markdown(
        "- Chaque équipe a une **force d'attaque** et une **force de défense**, calculées sur ses matchs des deux "
        "dernières saisons (les plus récents comptent plus), plus l'**avantage du terrain** de sa ligue.\n"
        "- **Vainqueur** : prolongations comprises (comme sur Betclic). **Temps réglementaire** : avec l'égalité "
        "possible à la fin du 4e quart-temps.\n"
        "- **Handicap −5,5** : l'équipe doit gagner de 6 points ou plus. **+5,5** : elle peut perdre de 5 points au plus.\n"
        "- **Pair ou impair** : impossible à prévoir, 50 % chacun.\n"
        "- Un pari n'est bon que si la cote Betclic est **plus haute que la cote juste**.")
