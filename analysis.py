"""Bellabeat case study - nettoyage + analyse (Fitbit, mars-mai 2016).
Usage: python analysis.py <dossier_raw> <dossier_sortie>
raw/p1 = export 3.12.16-4.11.16 ; raw/p2 = export 4.12.16-5.12.16
"""
import sys, json, os
import pandas as pd, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(f"{OUT}/images", exist_ok=True)
os.makedirs(f"{OUT}/data_clean", exist_ok=True)
log, R = [], {}

def note(step, issue, rule, before, after):
    log.append(dict(etape=step, probleme=issue, regle=rule, lignes_avant=before, lignes_apres=after))

# ---------- 1. CHARGEMENT ----------
a1 = pd.read_csv(f"{RAW}/p1/dailyActivity_merged.csv").assign(source="p1")
a2 = pd.read_csv(f"{RAW}/p2/dailyActivity_merged.csv").assign(source="p2")
sl = pd.read_csv(f"{RAW}/p2/sleepDay_merged.csv")
h1 = pd.read_csv(f"{RAW}/p1/hourlySteps_merged.csv").assign(source="p1")
h2 = pd.read_csv(f"{RAW}/p2/hourlySteps_merged.csv").assign(source="p2")

# ---------- 2. NETTOYAGE ----------
act = pd.concat([a1, a2], ignore_index=True)
act.columns = [c[0].lower() + c[1:] for c in act.columns]
act["date"] = pd.to_datetime(act["activityDate"], format="%m/%d/%Y")
R["users_activity_raw"] = int(act.id.nunique()); R["rows_activity_raw"] = len(act)
n0 = len(act)

# 2a. chevauchement du 12/04/2016 : on garde la version complete (periode 2)
act = act.sort_values(["id", "date", "source"]).drop_duplicates(["id", "date"], keep="last")
note("Doublons", "Le 12/04/2016 apparait dans les 2 exports avec des valeurs differentes (version p1 = journee partielle)",
     "Garder la ligne de l'export p2 (journee complete)", n0, len(act))

# 2b. jours sans port de l'appareil
n1 = len(act)
act["tracked_min"] = act.veryActiveMinutes + act.fairlyActiveMinutes + act.lightlyActiveMinutes + act.sedentaryMinutes
nonwear = act.totalSteps < 100
R["nonwear_days"] = int(nonwear.sum())
act = act[~nonwear].copy()
note("Valeurs aberrantes", "Jours a moins de 100 pas : appareil non porte (ex. 1440 min 'sedentaires' et 0 pas)",
     "Exclure les jours < 100 pas (seuil choisi par jugement)", n1, len(act))

# 2c. types / colonnes derivees
act["weekday"] = act.date.dt.day_name()
act["dow"] = act.date.dt.dayofweek
act["active_min"] = act.veryActiveMinutes + act.fairlyActiveMinutes
note("Transformation", "Dates en texte (M/J/AAAA)", "Conversion en date, ajout jour de semaine et minutes actives", len(act), len(act))

# sommeil
sl["date"] = pd.to_datetime(sl.SleepDay, format="%m/%d/%Y %I:%M:%S %p").dt.normalize()
s0 = len(sl)
sl = sl.drop_duplicates(["Id", "date"])
note("Doublons", "Lignes de sommeil dupliquees", "drop_duplicates sur (Id, date)", s0, len(sl))
sl = sl.rename(columns={"Id": "id", "TotalMinutesAsleep": "asleep_min", "TotalTimeInBed": "inbed_min", "TotalSleepRecords": "sleep_records"})
sl["efficiency"] = sl.asleep_min / sl.inbed_min

# heures
hr = pd.concat([h1, h2], ignore_index=True)
hr["ts"] = pd.to_datetime(hr.ActivityHour, format="%m/%d/%Y %I:%M:%S %p")
hr = hr.sort_values(["Id", "ts", "source"]).drop_duplicates(["Id", "ts"], keep="last")
hr["date"] = hr.ts.dt.normalize(); hr["hour"] = hr.ts.dt.hour
hr = hr.rename(columns={"Id": "id", "StepTotal": "steps"})
hr = hr.merge(act[["id", "date"]], on=["id", "date"], how="inner")   # jours valides uniquement
note("Jointure", "Pas par heure : garder seulement les jours valides", "INNER JOIN avec jours valides", "-", len(hr))

act.to_csv(f"{OUT}/data_clean/daily_activity_clean.csv", index=False)
sl.to_csv(f"{OUT}/data_clean/sleep_clean.csv", index=False)
pd.DataFrame(log).to_csv(f"{OUT}/data_clean/cleaning_log.csv", index=False)

R["users_valid"] = int(act.id.nunique()); R["days_valid"] = len(act)
R["date_min"] = str(act.date.min().date()); R["date_max"] = str(act.date.max().date())

# ---------- 3. ANALYSE ----------
# Q1a. profil moyen
R["mean_steps"] = round(act.totalSteps.mean()); R["median_steps"] = round(act.totalSteps.median())
R["mean_active_min"] = round(act.active_min.mean(), 1)
R["share_days_ge10k"] = round((act.totalSteps >= 10000).mean() * 100, 1)
R["share_days_ge7500"] = round((act.totalSteps >= 7500).mean() * 100, 1)

# Q1b. jour de la semaine
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
wd = act.groupby("weekday").agg(steps=("totalSteps", "mean"), n=("id", "size"), sed=("sedentaryMinutes", "mean")).reindex(order)
R["weekday_steps"] = wd.steps.round().to_dict(); R["weekday_n"] = wd.n.to_dict()

# Q1c. heure
hp = hr.groupby("hour").steps.mean()
R["peak_hours"] = hp.sort_values(ascending=False).head(4).round(1).to_dict()
R["hour_12_14_19"] = {h: round(hp[h], 1) for h in (8, 12, 13, 17, 18, 19)}
hp_we = hr.assign(we=hr.date.dt.dayofweek >= 5).groupby(["we", "hour"]).steps.mean().unstack(0)

# segments utilisateurs (classification usuelle par pas/jour : <5000 / 5000-7499 / 7500-9999 / >=10000)
u = act.groupby("id").agg(avg_steps=("totalSteps", "mean"), days=("date", "size"),
                          avg_sed=("sedentaryMinutes", "mean"), avg_cal=("calories", "mean"))
u["segment"] = pd.cut(u.avg_steps, [0, 5000, 7500, 10000, 1e9], right=False,
                      labels=["Sedentaire (<5 000)", "Peu actif (5 000-7 499)", "Assez actif (7 500-9 999)", "Actif (>=10 000)"])
seg = u.segment.value_counts().reindex(u.segment.cat.categories)
R["segments"] = seg.to_dict(); R["users_total_seg"] = int(len(u))

# Q2. sommeil x activite
m = sl.merge(act, on=["id", "date"], how="inner")
R["sleep_users"] = int(sl.id.nunique()); R["sleep_nights"] = len(sl); R["sleep_joined_nights"] = len(m)
R["sleep_users_joined"] = int(m.id.nunique())
tot = m[["veryActiveMinutes", "fairlyActiveMinutes", "lightlyActiveMinutes", "sedentaryMinutes"]].sum()
R["share_minutes_awake_basis"] = (tot / tot.sum() * 100).round(1).to_dict()
R["sed_awake_h"] = round(m.sedentaryMinutes.mean() / 60, 1); R["awake_tracked_h"] = round(m.tracked_min.mean() / 60, 1)
R["check_tracked_plus_inbed_median_gap_min"] = float((1440 - m.tracked_min - m.inbed_min).median())
R["mean_asleep_h"] = round(m.asleep_min.mean() / 60, 2); R["mean_inbed_h"] = round(m.inbed_min.mean() / 60, 2)
R["mean_efficiency_pct"] = round(m.efficiency.mean() * 100, 1)
R["share_nights_lt7h"] = round((m.asleep_min < 420).mean() * 100, 1)
R["mean_wait_to_sleep_min"] = round((m.inbed_min - m.asleep_min).mean(), 1)
R["median_wait_to_sleep_min"] = round((m.inbed_min - m.asleep_min).median(), 1)
cor = {}
for c in ["totalSteps", "veryActiveMinutes", "active_min", "sedentaryMinutes", "calories"]:
    cor[c] = dict(pearson=round(m[c].corr(m.asleep_min), 3), spearman=round(m[c].corr(m.asleep_min, method="spearman"), 3))
R["corr_with_asleep"] = cor
cor_bed = round(m.sedentaryMinutes.corr(m.inbed_min), 3)
R["corr_sed_inbed_ARTEFACT"] = cor_bed
s2 = sl.copy(); s2["date"] = s2.date - pd.Timedelta(days=1)
L = s2.merge(act, on=["id", "date"])
R["lag_steps_vs_next_night"] = dict(n=len(L), pearson=round(L.totalSteps.corr(L.asleep_min), 3), spearman=round(L.totalSteps.corr(L.asleep_min, method="spearman"), 3))
xx = m.totalSteps - m.groupby("id").totalSteps.transform("mean"); yy = m.asleep_min - m.groupby("id").asleep_min.transform("mean")
R["within_user_steps_sleep_sameday"] = round(xx.corr(yy), 3)
from scipy import stats
R["kruskal_weekday_p"] = round(stats.kruskal(*[g.totalSteps.values for _, g in act.groupby("weekday")]).pvalue, 3)
# garde-fou : minutes sedentaires incluent le sommeil ? -> comparer avec nuits courtes
m["steps_bin"] = pd.cut(m.totalSteps, [0, 5000, 10000, 15000, 1e9], right=False, labels=["<5k", "5-10k", "10-15k", ">=15k"])
sb = m.groupby("steps_bin", observed=True).agg(asleep_h=("asleep_min", lambda s: s.mean() / 60), n=("id", "size"))
R["sleep_by_steps_bin"] = sb.round(2).to_dict("index")
# par utilisateur (evite qu'un utilisateur pese par ses nombreuses nuits)
mu = m.groupby("id").agg(steps=("totalSteps", "mean"), asleep=("asleep_min", "mean"), n=("id", "size"))
R["corr_user_level_steps_sleep"] = round(mu.steps.corr(mu.asleep), 3); R["users_user_level"] = int(len(mu))

# Q3. regularite d'utilisation
rec = pd.concat([a1, a2]).assign(date=lambda d: pd.to_datetime(d.ActivityDate, format="%m/%d/%Y"))
rec = rec.drop_duplicates(["Id", "date"])
all_days = rec.groupby("Id").size().rename("recorded_days")
valid_days = act.groupby("id").size().rename("valid_days")
uu = pd.concat([all_days, valid_days], axis=1).fillna(0)
uu["wear_rate"] = uu.valid_days / uu.recorded_days
R["users_recorded"] = int(len(uu)); R["median_valid_days"] = float(uu.valid_days.median())
R["share_users_wear_ge90"] = round((uu.wear_rate >= 0.9).mean() * 100, 1)
R["share_users_wear_ge80"] = round((uu.wear_rate >= 0.8).mean() * 100, 1)
R["overall_wear_rate"] = round(uu.valid_days.sum() / uu.recorded_days.sum() * 100, 1)
p2_users = set(a2.Id)
R["users_p2"] = len(p2_users); R["sleep_adoption_pct"] = round(len(set(sl.id)) / len(p2_users) * 100, 1)
nights = sl.groupby("id").size()
R["median_nights_per_sleep_user"] = float(nights.median())
R["share_sleep_users_ge20nights"] = round((nights >= 20).mean() * 100, 1)
# fatigue d'usage : jours valides par semaine
act["week"] = ((act.date - act.date.min()).dt.days // 7)
wk = act.groupby("week").id.nunique()
R["active_users_by_week"] = wk.to_dict()

# ---------- 4. GRAPHIQUES ----------
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 13})
C_MAIN, C_HI, C_GREY = "#B4506B", "#2F4858", "#C9CED3"

# G1 pas par jour
fig, ax = plt.subplots(figsize=(8, 4.4))
fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
vals = wd.steps.values; best = vals.argmax(); worst = vals.argmin()
cols = [C_GREY] * 7; cols[best] = C_MAIN; cols[worst] = C_HI
b = ax.bar(fr, vals, color=cols)
for r, v in zip(b, vals): ax.text(r.get_x() + r.get_width() / 2, v + 90, f"{v:,.0f}".replace(",", " "), ha="center", fontsize=9)
ax.set_title(f"{['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'][best]} : jour le plus actif ; {['lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche'][worst]} : le moins actif")
ax.set_ylabel("Pas par jour (moyenne)"); ax.set_ylim(0, vals.max() * 1.15)
fig.text(0.01, -0.02, f"Source : Fitbit (Mobius), {R['users_valid']} utilisateurs, {R['days_valid']} jours valides.", fontsize=8, color="#666")
fig.tight_layout(); fig.savefig(f"{OUT}/images/01_pas_par_jour.png", dpi=160, bbox_inches="tight"); plt.close()

# G2 profil horaire
fig, ax = plt.subplots(figsize=(8.5, 4.4))
ax.plot(hp_we.index, hp_we[False], color=C_MAIN, lw=2.4, label="Semaine")
ax.plot(hp_we.index, hp_we[True], color=C_HI, lw=2.4, ls="--", label="Week-end")
ax.set_xticks(range(0, 24, 2)); ax.set_xticklabels([f"{h}h" for h in range(0, 24, 2)])
ax.set_ylabel("Pas par heure (moyenne)"); ax.legend(frameon=False)
tw = hp_we[False].idxmax(); tn = hp_we[True].idxmax()
R["weekday_peak"] = [int(tw), round(float(hp_we[False][tw]))]; R["weekend_peak"] = [int(tn), round(float(hp_we[True][tn]))]
R["weekday_dip_15h"] = round(float(hp_we[False][15])); R["weekday_noon_12h"] = round(float(hp_we[False][12]))
ax.set_title("En semaine, deux pics (midi et 18-19 h) ; le week-end, un plateau de 10 h à 14 h")
ax.annotate(f"Pic semaine : {tw}h", (tw, hp_we[False][tw]), xytext=(tw - 6.5, hp_we[False][tw] + 35), arrowprops=dict(arrowstyle="->", color="#444"), fontsize=9)
ax.set_ylim(0, hp_we.max().max() * 1.2)
fig.tight_layout(); fig.savefig(f"{OUT}/images/02_profil_horaire.png", dpi=160, bbox_inches="tight"); plt.close()

# G3 segments
fig, ax = plt.subplots(figsize=(8, 4))
lab = list(seg.index); v = seg.values
cc = [C_GREY, C_GREY, C_GREY, C_GREY]; cc[int(np.argmax(v))] = C_MAIN
b = ax.barh(lab[::-1], v[::-1], color=cc[::-1])
for r, x in zip(b, v[::-1]): ax.text(x + 0.15, r.get_y() + r.get_height() / 2, f"{x} ({x / len(u) * 100:.0f} %)", va="center", fontsize=9)
ax.set_xlabel("Nombre d'utilisateurs"); ax.set_xlim(0, v.max() * 1.25)
ax.set_title("Où se situent les utilisateurs selon leurs pas quotidiens ?")
fig.tight_layout(); fig.savefig(f"{OUT}/images/03_segments_utilisateurs.png", dpi=160, bbox_inches="tight"); plt.close()

# G4 sommeil x pas
fig, ax = plt.subplots(figsize=(7.5, 4.6))
ax.scatter(m.totalSteps, m.asleep_min / 60, s=18, alpha=.45, color=C_MAIN)
z = np.polyfit(m.totalSteps, m.asleep_min / 60, 1); xs = np.linspace(0, m.totalSteps.max(), 50)
ax.plot(xs, np.polyval(z, xs), color=C_HI, lw=2)
ax.axhline(7, color="#888", ls=":", lw=1); ax.text(m.totalSteps.max() * 0.62, 7.12, "7 h de sommeil", fontsize=8, color="#555")
r_ = cor["totalSteps"]["pearson"]
ax.set_title(f"Pas et durée de sommeil : lien très faible (r = {r_})")
ax.set_xlabel("Pas dans la journée"); ax.set_ylabel("Heures de sommeil la nuit")
fig.tight_layout(); fig.savefig(f"{OUT}/images/04_sommeil_vs_pas.png", dpi=160, bbox_inches="tight"); plt.close()

# G5 utilisation
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(uu.wear_rate * 100, bins=np.arange(0, 105, 10), color=C_MAIN, edgecolor="white")
ax.set_xlabel("% de jours où l'appareil a été porté (par utilisateur)"); ax.set_ylabel("Nombre d'utilisateurs")
ax.set_title(f"{R['share_users_wear_ge80']:.0f} % des utilisateurs portent l'appareil au moins 80 % des jours")
fig.tight_layout(); fig.savefig(f"{OUT}/images/05_regularite_port.png", dpi=160, bbox_inches="tight"); plt.close()

json.dump(R, open(f"{OUT}/data_clean/results.json", "w"), indent=1, default=str, ensure_ascii=False)
print(json.dumps(R, indent=1, default=str, ensure_ascii=False))
print(pd.DataFrame(log).to_string())
