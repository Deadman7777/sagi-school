"""
Seed des données de référence du Coran : 114 sourates + subdivisions
(Juz 30, Hizb 60, Nisf 60, Rub' 240) pour Hafs et Warsh.

Idempotent (update_or_create). Données partagées (non multi-tenant).

    python manage.py init_coran          # crée / met à jour
    python manage.py init_coran --force  # idem (réservé pour usages futurs)

NOTE données :
- nb_versets_hafs : comptage Kufi/Hafs (total 6236).
- nb_versets_warsh : initialisé = Hafs (baseline). Warsh suit le comptage
  Madani al-akhir (total 6214 ; écart = comptage des fawatih/basmala, AUCUNE
  différence de texte). Faute de table par sourate vérifiée et machine-lisible,
  on garde Hafs (impact ~0,35 % sur le % mémorisé).
- Subdivisions : bornes Juz/Hizb/Nisf/Rub' issues de Tanzil.net (CC-BY),
  embarquées dans coran_subdivisions.py. Numérotation des versets = Hafs ;
  positions physiques identiques pour Warsh.
"""
from django.core.management.base import BaseCommand

from apps.daara.models import Sourate, Subdivision
from apps.daara.coran_subdivisions import JUZ, HIZB, NISF, RUB

# (numero, nom_ar, nom_fr, type_revelation, nb_versets_hafs)
SOURATES = [
    (1,  'الفاتحة', 'Al-Fatiha', 'MECQUOISE', 7),
    (2,  'البقرة', 'Al-Baqara', 'MEDINOISE', 286),
    (3,  'آل عمران', "Al-Imran", 'MEDINOISE', 200),
    (4,  'النساء', 'An-Nisa', 'MEDINOISE', 176),
    (5,  'المائدة', "Al-Ma'ida", 'MEDINOISE', 120),
    (6,  'الأنعام', "Al-An'am", 'MECQUOISE', 165),
    (7,  'الأعراف', "Al-A'raf", 'MECQUOISE', 206),
    (8,  'الأنفال', 'Al-Anfal', 'MEDINOISE', 75),
    (9,  'التوبة', 'At-Tawba', 'MEDINOISE', 129),
    (10, 'يونس', 'Yunus', 'MECQUOISE', 109),
    (11, 'هود', 'Hud', 'MECQUOISE', 123),
    (12, 'يوسف', 'Yusuf', 'MECQUOISE', 111),
    (13, 'الرعد', "Ar-Ra'd", 'MEDINOISE', 43),
    (14, 'إبراهيم', 'Ibrahim', 'MECQUOISE', 52),
    (15, 'الحجر', 'Al-Hijr', 'MECQUOISE', 99),
    (16, 'النحل', 'An-Nahl', 'MECQUOISE', 128),
    (17, 'الإسراء', 'Al-Isra', 'MECQUOISE', 111),
    (18, 'الكهف', 'Al-Kahf', 'MECQUOISE', 110),
    (19, 'مريم', 'Maryam', 'MECQUOISE', 98),
    (20, 'طه', 'Ta-Ha', 'MECQUOISE', 135),
    (21, 'الأنبياء', 'Al-Anbiya', 'MECQUOISE', 112),
    (22, 'الحج', 'Al-Hajj', 'MEDINOISE', 78),
    (23, 'المؤمنون', "Al-Mu'minun", 'MECQUOISE', 118),
    (24, 'النور', 'An-Nur', 'MEDINOISE', 64),
    (25, 'الفرقان', 'Al-Furqan', 'MECQUOISE', 77),
    (26, 'الشعراء', "Ash-Shu'ara", 'MECQUOISE', 227),
    (27, 'النمل', 'An-Naml', 'MECQUOISE', 93),
    (28, 'القصص', 'Al-Qasas', 'MECQUOISE', 88),
    (29, 'العنكبوت', 'Al-Ankabut', 'MECQUOISE', 69),
    (30, 'الروم', 'Ar-Rum', 'MECQUOISE', 60),
    (31, 'لقمان', 'Luqman', 'MECQUOISE', 34),
    (32, 'السجدة', 'As-Sajda', 'MECQUOISE', 30),
    (33, 'الأحزاب', 'Al-Ahzab', 'MEDINOISE', 73),
    (34, 'سبأ', 'Saba', 'MECQUOISE', 54),
    (35, 'فاطر', 'Fatir', 'MECQUOISE', 45),
    (36, 'يس', 'Ya-Sin', 'MECQUOISE', 83),
    (37, 'الصافات', 'As-Saffat', 'MECQUOISE', 182),
    (38, 'ص', 'Sad', 'MECQUOISE', 88),
    (39, 'الزمر', 'Az-Zumar', 'MECQUOISE', 75),
    (40, 'غافر', 'Ghafir', 'MECQUOISE', 85),
    (41, 'فصلت', 'Fussilat', 'MECQUOISE', 54),
    (42, 'الشورى', 'Ash-Shura', 'MECQUOISE', 53),
    (43, 'الزخرف', 'Az-Zukhruf', 'MECQUOISE', 89),
    (44, 'الدخان', 'Ad-Dukhan', 'MECQUOISE', 59),
    (45, 'الجاثية', 'Al-Jathiya', 'MECQUOISE', 37),
    (46, 'الأحقاف', 'Al-Ahqaf', 'MECQUOISE', 35),
    (47, 'محمد', 'Muhammad', 'MEDINOISE', 38),
    (48, 'الفتح', 'Al-Fath', 'MEDINOISE', 29),
    (49, 'الحجرات', 'Al-Hujurat', 'MEDINOISE', 18),
    (50, 'ق', 'Qaf', 'MECQUOISE', 45),
    (51, 'الذاريات', 'Adh-Dhariyat', 'MECQUOISE', 60),
    (52, 'الطور', 'At-Tur', 'MECQUOISE', 49),
    (53, 'النجم', 'An-Najm', 'MECQUOISE', 62),
    (54, 'القمر', 'Al-Qamar', 'MECQUOISE', 55),
    (55, 'الرحمن', 'Ar-Rahman', 'MEDINOISE', 78),
    (56, 'الواقعة', "Al-Waqi'a", 'MECQUOISE', 96),
    (57, 'الحديد', 'Al-Hadid', 'MEDINOISE', 29),
    (58, 'المجادلة', 'Al-Mujadila', 'MEDINOISE', 22),
    (59, 'الحشر', 'Al-Hashr', 'MEDINOISE', 24),
    (60, 'الممتحنة', 'Al-Mumtahana', 'MEDINOISE', 13),
    (61, 'الصف', 'As-Saff', 'MEDINOISE', 14),
    (62, 'الجمعة', "Al-Jumu'a", 'MEDINOISE', 11),
    (63, 'المنافقون', 'Al-Munafiqun', 'MEDINOISE', 11),
    (64, 'التغابن', 'At-Taghabun', 'MEDINOISE', 18),
    (65, 'الطلاق', 'At-Talaq', 'MEDINOISE', 12),
    (66, 'التحريم', 'At-Tahrim', 'MEDINOISE', 12),
    (67, 'الملك', 'Al-Mulk', 'MECQUOISE', 30),
    (68, 'القلم', 'Al-Qalam', 'MECQUOISE', 52),
    (69, 'الحاقة', 'Al-Haqqa', 'MECQUOISE', 52),
    (70, 'المعارج', "Al-Ma'arij", 'MECQUOISE', 44),
    (71, 'نوح', 'Nuh', 'MECQUOISE', 28),
    (72, 'الجن', 'Al-Jinn', 'MECQUOISE', 28),
    (73, 'المزمل', 'Al-Muzzammil', 'MECQUOISE', 20),
    (74, 'المدثر', 'Al-Muddaththir', 'MECQUOISE', 56),
    (75, 'القيامة', 'Al-Qiyama', 'MECQUOISE', 40),
    (76, 'الإنسان', 'Al-Insan', 'MEDINOISE', 31),
    (77, 'المرسلات', 'Al-Mursalat', 'MECQUOISE', 50),
    (78, 'النبأ', 'An-Naba', 'MECQUOISE', 40),
    (79, 'النازعات', "An-Nazi'at", 'MECQUOISE', 46),
    (80, 'عبس', 'Abasa', 'MECQUOISE', 42),
    (81, 'التكوير', 'At-Takwir', 'MECQUOISE', 29),
    (82, 'الانفطار', 'Al-Infitar', 'MECQUOISE', 19),
    (83, 'المطففين', 'Al-Mutaffifin', 'MECQUOISE', 36),
    (84, 'الانشقاق', 'Al-Inshiqaq', 'MECQUOISE', 25),
    (85, 'البروج', 'Al-Buruj', 'MECQUOISE', 22),
    (86, 'الطارق', 'At-Tariq', 'MECQUOISE', 17),
    (87, 'الأعلى', "Al-A'la", 'MECQUOISE', 19),
    (88, 'الغاشية', 'Al-Ghashiya', 'MECQUOISE', 26),
    (89, 'الفجر', 'Al-Fajr', 'MECQUOISE', 30),
    (90, 'البلد', 'Al-Balad', 'MECQUOISE', 20),
    (91, 'الشمس', 'Ash-Shams', 'MECQUOISE', 15),
    (92, 'الليل', 'Al-Layl', 'MECQUOISE', 21),
    (93, 'الضحى', 'Ad-Duha', 'MECQUOISE', 11),
    (94, 'الشرح', 'Ash-Sharh', 'MECQUOISE', 8),
    (95, 'التين', 'At-Tin', 'MECQUOISE', 8),
    (96, 'العلق', 'Al-Alaq', 'MECQUOISE', 19),
    (97, 'القدر', 'Al-Qadr', 'MECQUOISE', 5),
    (98, 'البينة', 'Al-Bayyina', 'MEDINOISE', 8),
    (99, 'الزلزلة', 'Az-Zalzala', 'MEDINOISE', 8),
    (100, 'العاديات', 'Al-Adiyat', 'MECQUOISE', 11),
    (101, 'القارعة', "Al-Qari'a", 'MECQUOISE', 11),
    (102, 'التكاثر', 'At-Takathur', 'MECQUOISE', 8),
    (103, 'العصر', 'Al-Asr', 'MECQUOISE', 3),
    (104, 'الهمزة', 'Al-Humaza', 'MECQUOISE', 9),
    (105, 'الفيل', 'Al-Fil', 'MECQUOISE', 5),
    (106, 'قريش', 'Quraysh', 'MECQUOISE', 4),
    (107, 'الماعون', "Al-Ma'un", 'MECQUOISE', 7),
    (108, 'الكوثر', 'Al-Kawthar', 'MECQUOISE', 3),
    (109, 'الكافرون', 'Al-Kafirun', 'MECQUOISE', 6),
    (110, 'النصر', 'An-Nasr', 'MEDINOISE', 3),
    (111, 'المسد', 'Al-Masad', 'MECQUOISE', 5),
    (112, 'الإخلاص', 'Al-Ikhlas', 'MECQUOISE', 4),
    (113, 'الفلق', 'Al-Falaq', 'MECQUOISE', 5),
    (114, 'الناس', 'An-Nas', 'MECQUOISE', 6),
]

# (type Subdivision -> liste de bornes (numero, sourate, verset)) issues de Tanzil.
SUBDIVISIONS = {'JUZ': JUZ, 'HIZB': HIZB, 'NISF': NISF, 'RUB': RUB}


class Command(BaseCommand):
    help = "Seed des sourates (114) et subdivisions (Juz/Hizb/Nisf/Rub') du Coran."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help="Force la réécriture (idempotent de toute façon).")

    def handle(self, *args, **options):
        for numero, nom_ar, nom_fr, type_rev, versets in SOURATES:
            Sourate.objects.update_or_create(
                numero=numero,
                defaults={
                    'nom_ar': nom_ar,
                    'nom_fr': nom_fr,
                    'type_revelation': type_rev,
                    'nb_versets_hafs': versets,
                    'nb_versets_warsh': versets,   # baseline = Hafs (cf. note module)
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Sourates : {Sourate.objects.count()}/114"))

        sourates = {s.numero: s for s in Sourate.objects.all()}
        for riwaya in ('HAFS', 'WARSH'):
            for type_, bornes in SUBDIVISIONS.items():
                for numero, s_num, verset in bornes:
                    Subdivision.objects.update_or_create(
                        riwaya=riwaya, type=type_, numero=numero,
                        defaults={'sourate_debut': sourates[s_num], 'verset_debut': verset},
                    )
        for type_, bornes in SUBDIVISIONS.items():
            n = Subdivision.objects.filter(type=type_).count()
            self.stdout.write(self.style.SUCCESS(
                f"Subdivisions {type_} : {n} ({len(bornes)} × 2 riwaaya)"
            ))
