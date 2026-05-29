"""Shared translation table and lookup for all Sensor Suite entry points."""

_T = {
    "title":    {"de": "Wasserwaage",          "en": "Spirit Level"},
    "level":    {"de": "eben",                 "en": "level"},
    "slight":   {"de": "leicht geneigt",       "en": "slightly tilted"},
    "tilted":   {"de": "geneigt",              "en": "tilted"},
    "cal_done": {"de": "Nullpunkt gesetzt",    "en": "Zero point set"},
    "s_ttl":    {"de": "Einstellungen",        "en": "Settings"},
    "s_appear": {"de": "Darstellung",          "en": "Appearance"},
    "s_theme":  {"de": "Design",               "en": "Theme"},
    "s_t_auto": {"de": "Automatisch",          "en": "Automatic"},
    "s_t_lt":   {"de": "Hell",                 "en": "Light"},
    "s_t_dk":   {"de": "Dunkel",               "en": "Dark"},
    "s_lang":   {"de": "Sprache",              "en": "Language"},
    "s_units":  {"de": "Einheiten",            "en": "Units"},
    "s_unit_metric":   {"de": "Metrisch",      "en": "Metric"},
    "s_unit_imperial": {"de": "Meilen",        "en": "Miles"},
    "s_cal":    {"de": "Kalibrierung",         "en": "Calibration"},
    "s_c_ttl":  {"de": "Nullpunkt setzen",     "en": "Set zero point"},
    "s_c_sub":  {"de": "Aktuelle Lage als Referenz übernehmen",
                 "en": "Use current position as reference"},
    "s_c_btn":  {"de": "Kalibrieren",          "en": "Calibrate"},
    "cal_tap":  {"de": "Bildschirm antippen – Nullpunkt setzen",
                 "en": "Tap screen to set zero point"},
    # pages
    "p_compass": {"de": "Kompass",      "en": "Compass"},
    "p_level":   {"de": "Wasserwaage",  "en": "Spirit Level"},
    "p_gforce":  {"de": "G-Kraft",      "en": "G-Force"},
    # menu
    "m_about":   {"de": "Über",         "en": "About"},
    # buttons
    "btn_cancel": {"de": "Abbrechen",   "en": "Cancel"},
    "btn_start":  {"de": "Starten",     "en": "Start"},
    "btn_skip":   {"de": "Überspringen", "en": "Skip"},
    # compass calibration dialog
    "dlg_cmp_ttl":  {"de": "Kompass kalibrieren", "en": "Calibrate Compass"},
    "dlg_cmp_body": {"de": "Gerät flach halten und langsam eine Acht in die Luft "
                           "zeichnen, bis alle drei Sterne gefüllt sind.",
                     "en": "Hold the device flat and slowly draw a figure-8 in the "
                           "air until all three stars are filled."},
    # spirit level calibration dialog
    "dlg_lvl_ttl":  {"de": "Wasserwaage kalibrieren", "en": "Calibrate Spirit Level"},
    "dlg_lvl_body": {"de": "Gerät in die Referenzlage bringen, dann den Bildschirm "
                           "antippen, um den Nullpunkt zu setzen.",
                     "en": "Place the device in the reference position, then tap "
                           "the screen to set the zero point."},
    # spirit level calibration done dialog
    "dlg_done_ttl":  {"de": "Kalibrierung abgeschlossen", "en": "Calibration Complete"},
    "dlg_done_body": {"de": "Der Nullpunkt wurde erfolgreich gesetzt.",
                      "en": "The zero point has been set successfully."},
    # compass calibration banner / status
    "cal_status":   {"de": "Kalibrierung",  "en": "Calibration"},
    "cal_hold":     {"de": "Gerät flach halten – langsam eine Acht in die Luft zeichnen",
                     "en": "Hold device flat — slowly draw a figure-8 in the air"},
    "cal_complete": {"de": "✓ Kalibrierung abgeschlossen", "en": "✓ Calibration complete"},
    "cal_fig8_0":   {"de": "Acht zeichnen – Gerät in alle Richtungen kippen",
                     "en": "Draw a figure-8 — tilt device in all directions"},
    "cal_fig8_1":   {"de": "Gut – die Acht ein- bis zweimal wiederholen",
                     "en": "Good — repeat the figure-8 one or two more times"},
    "cal_fig8_2":   {"de": "Fast fertig – noch eine Runde",
                     "en": "Almost done — one more round"},
    # about
    "about_comments": {"de": "Kompass · Wasserwaage · G-Kraft",
                       "en": "Compass · Spirit Level · G-Force"},
    "no_gps": {"de": "Kein GPS Signal", "en": "No GPS signal"},
    "s_speed":   {"de": "Geschwindigkeit", "en": "Speed"},
    "demo_none": {"de": "Demo-Modus – kein Magnetometer gefunden",
                  "en": "Demo mode — no magnetometer found"},
}


def _(key, lang):
    return _T.get(key, {}).get(lang, key)
