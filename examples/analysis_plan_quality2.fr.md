## PLAN D'ANALYSE PRÉ-ENREGISTRÉ (2 août 11 h 05, AVANT tout résultat cheap2/v7)

Écrit et committé avant que le moindre fit Kaggle de la paire n'ait produit un chiffre. Les prédictions pré-enregistrées du PC fixe (WORKPLAN_v02.md, intouchable) seront confrontées EN PLUS quand récupérées ; le présent plan est celui qui engage l'analyse.

**Les trois comparaisons, toutes sur les mêmes 94 patches scellés (v1), bootstrap apparié 20 000 tirages `--unseen`** :
1. cheap2 vs quality2 (v7) : LA preuve, plateforme pure (même T4, même image, mêmes graines, seul num_training_steps change, 1 500 contre 6 000).
2. smoke8 vs quality2 : la comparaison avec la référence publiée.
3. smoke8 vs cheap2 : isole l'effet plateforme (3060 Ti/eager contre T4/triton, config identique).

**Règles de décision, figées maintenant** :
- « L'outil classe le run long au-dessus » = les écarts de distance appariés (p50 et p99 par patch, moyenne pondérée par points) favorisent quality2 avec un intervalle bootstrap excluant zéro sur la comparaison 1.
- Si les écarts favorisent quality2 mais traversent zéro : on publie « cohérent mais non concluant au bootstrap », pas de survente, et c'est un résultat honnête acceptable.
- Si les écarts sont nuls ou favorisent cheap2 : on le publie tel quel, avec l'hypothèse à examiner (1 500 pas suffisent peut-être à converger sur une fenêtre de 300 tranches ; les pertes différées ne s'activant qu'à 25 000, le budget 6 000 n'ajoute peut-être que du polissage). Un outil d'évaluation qui découvre que « plus long ne veut pas dire meilleur » sur cette fenêtre reste une découverte valide de l'outil.
- La comparaison 3 (plateforme) n'a AUCUNE règle de victoire : elle est descriptive, pour borner ce que la comparaison 2 peut dire.
- Métriques secondaires (within-tau, cohérence de feuille, normales) : rapportées avec leurs intervalles, jamais promues en critère principal après coup.
- Aucune métrique nouvelle ne sera calculée après avoir vu les résultats ; tout écart au plan sera signalé comme tel.
