-- Équivalents BigQuery des étapes clés (NON exécutés dans ce projet : l'analyse a été faite en Python).
-- À adapter : remplacer `projet.dataset` par le vôtre. Tables supposées chargées depuis les CSV,
-- avec ActivityDate converti en DATE (PARSE_DATE('%m/%d/%Y', ActivityDate)).

-- 1. Jours valides (non-port exclu) + dédoublonnage du 12/04 (on garde l'export 2)
CREATE OR REPLACE VIEW `projet.dataset.daily_clean` AS
SELECT * EXCEPT(rn) FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY Id, activity_date ORDER BY source DESC) AS rn
  FROM `projet.dataset.daily_activity_all`            -- p1 UNION ALL p2, avec colonne source
)
WHERE rn = 1 AND TotalSteps >= 100;

-- 2. Pas moyens par jour de la semaine
SELECT FORMAT_DATE('%A', activity_date) AS jour, ROUND(AVG(TotalSteps)) AS pas_moyens, COUNT(*) AS n
FROM `projet.dataset.daily_clean`
GROUP BY jour ORDER BY pas_moyens DESC;

-- 3. Sommeil + activité (jointure sur utilisateur et date) ; LEFT JOIN pour mesurer l'adoption du suivi du sommeil
SELECT a.Id,
       COUNT(a.activity_date) AS jours_valides,
       COUNT(s.sleep_date)    AS nuits_enregistrees,
       ROUND(AVG(s.TotalMinutesAsleep)/60, 2) AS heures_sommeil
FROM `projet.dataset.daily_clean` a
LEFT JOIN `projet.dataset.sleep_clean` s ON a.Id = s.Id AND a.activity_date = s.sleep_date
GROUP BY a.Id;

-- 4. Segmentation des utilisateurs par pas quotidiens moyens
SELECT segment, COUNT(*) AS utilisateurs FROM (
  SELECT Id, CASE WHEN AVG(TotalSteps) < 5000 THEN '1. Sédentaire (<5 000)'
                  WHEN AVG(TotalSteps) < 7500 THEN '2. Peu actif (5 000-7 499)'
                  WHEN AVG(TotalSteps) < 10000 THEN '3. Assez actif (7 500-9 999)'
                  ELSE '4. Actif (>=10 000)' END AS segment
  FROM `projet.dataset.daily_clean` GROUP BY Id)
GROUP BY segment ORDER BY segment;
