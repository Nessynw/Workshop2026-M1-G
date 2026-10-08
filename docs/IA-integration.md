# Intégration du Random Forest

Le modèle `random_forest_sentinel.joblib` et les notebooks proviennent de la branche `data` de la collègue. Ils sont conservés sans réentraînement. Le modèle exporté utilise scikit-learn 1.9.1 ; cette version est fixée dans les dépendances.

Le bridge analyse chaque mesure avec huit variables : température, humidité, gaz brut, leurs trois variations immédiates et les variations de température et de gaz sur cinq intervalles. Six mesures consécutives sont donc nécessaires avant la première prédiction. Un redémarrage de compteur, une mesure manquante, une rupture des variations ou une interruption de plus de dix secondes réinitialisent cet historique. Les sources et les modes ont des historiques distincts.

Le modèle classe les mesures en `NORMAL`, `PRE_ALERTE`, `SURCHAUFFE`, `FUITE_GAZ` ou `INCIDENT_COMBINE`. Le PIR reste affiché séparément : la présence n'est pas une variable du modèle final. La confiance affichée est la probabilité de la classe prédite, pas une précision mesurée en production. Les changements de classe à risque créent des événements persistants dans l'API, sans répéter la même alerte pour chaque mesure.

L'analyse fonctionne en mode générateur et en mode capteurs. Les données d'entraînement proviennent de Wokwi. L'inférence sur le matériel réel nécessite une validation indépendante : les valeurs du gaz ne sont pas des ppm calibrés. Les variations correspondent à cinq observations et non à une durée fixe ; le générateur publie à 0,2 seconde et le mode capteurs à deux secondes.

Le notebook rapporte 99,67 % d'accord sur 305 observations réservées par séquence. Les cibles ont été définies par des règles et le choix des séquences de test a été ajusté dans le notebook. Ce résultat documente ce jeu de test déjà consulté, sans prouver la prédiction d'incidents réels.

## Vérification et lancement

Depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe validate_random_forest.py
docker compose up -d --build
.\.venv\Scripts\python.exe mqtt_bridge.py
```

Relancer la caméra dans un autre terminal et la simulation Wokwi. Après six mesures, le dashboard affiche la classe prédite et sa confiance. Le rapport de rejeu est enregistré dans `models/random_forest_integration_report.json`. L'accès au dashboard, les autorisations des services et les échanges MQTTS restent actifs.
