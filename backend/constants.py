"""Reference data for report-card conduct and work-habit items (A1.7a).

Each item is ``(item_key, label_en, label_fr)``. ``item_key`` is what gets
stored in the ``report_conduct_items`` / ``report_work_habit_items`` tables; the
labels are display data owned by the backend and returned in the report
response so the admin UI never has to duplicate them.
"""

CONDUCT_ITEMS = [
    ("controls_talking", "Controls talking", "Contrôle de langage"),
    ("respects_authority", "Respects Authority", "Respect de l'autorité"),
    ("practices_self_control", "Practices self control", "Maîtrise de soi"),
    ("follows_directions", "Follow directions", "Suivi des consignes"),
    ("behaves_in_dismissal", "Behaves in dismissal group", "Attitude à la fin des classes"),
    ("behaves_in_cafeteria", "Behaves in cafeteria", "Attitude pendant la récréation et à la cantine"),
]

WORK_HABIT_ITEMS = [
    ("good_listening", "Practice good listening habits", "Pratique une bonne écoute"),
    ("works_with_others", "Works and plays well with others", "Bonne collaboration avec les autres"),
    ("uses_time_well", "Makes good use of time", "Fait bon usage du temps"),
    ("works_independently", "Works independently", "Travail de façon indépendante"),
    ("takes_pride", "Takes pride in his/her work", "Fier de son travail"),
    ("completes_on_time", "Completes work in a timely manner", "Fini le travail à temps"),
    ("returns_homework", "Returns homework daily", "Fait et ramène les devoirs de maison chaque jour"),
]

CONDUCT_ITEM_KEYS = [key for key, _, _ in CONDUCT_ITEMS]
WORK_HABIT_ITEM_KEYS = [key for key, _, _ in WORK_HABIT_ITEMS]
