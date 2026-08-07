## AICP Research 1.3.6

Diese Version arbeitet die Ergebnisse eines ausführlichen Tests ab – vor allem beim sicheren Weitergeben von Büchern, bei zitierfähigen Seitenzahlen und beim zuverlässigen Einlesen.

### Sicherheit und Daten
- **Auswahl-Export gibt wirklich nur die Auswahl weiter:** Beim Exportieren ausgewählter Bücher enthielt die Datei bisher versehentlich die **gesamte** Bibliothek, alle Lesezeichen und persönliche Daten (inklusive gespeicherter Zugangsdaten des Online-Servers). Jetzt enthält der Export ausschließlich die gewählten Bücher und ihre Lesezeichen – nichts weiter. Auch die Dateigröße ist entsprechend kleiner.

### Zuverlässiges Einlesen und Seitenzahlen
- **Alte Bücher wieder neu einlesbar:** Bücher, die vor der Umbenennung der App importiert wurden, ließen sich nicht mehr neu einlesen oder im Original öffnen („Originaldatei nicht mehr auffindbar"). Die App findet die Dateien jetzt automatisch wieder.
- **Textdateien ehrlich gekennzeichnet:** Eine `.txt`-Datei hat keine gedruckten Seiten. Ihre Seitenangaben werden jetzt als **„ungefähr"** ausgewiesen statt fälschlich als zitierfähig.
- **Kaputte Vorlagen werden erkannt:** Seiten, deren Textebene nur Zeichensalat liefert, werden jetzt zuverlässig erkannt und per Texterkennung lesbar gemacht – nicht mehr unbrauchbar in die Bibliothek übernommen.
- **Leere Dokumente werden gemeldet** statt still und ohne Inhalt in der Bibliothek zu landen.
- **Verständliche Meldungen:** Beschädigte, leere oder passwortgeschützte Dateien erzeugen jetzt klare deutsche bzw. arabische Hinweise statt englischer Technik-Meldungen.

### Leser und Suche
- **Richtige Seitenzahl sofort:** Nach dem Anklicken eines Treffers zeigte der Leser kurz eine um 1 zu niedrige Seitenzahl. Jetzt steht sofort die richtige Seite oben.
- **„Neu einlesen" robuster:** Mehrfaches Klicken führt nicht mehr zu einem leeren, endlos ladenden Leser; die Zeile bleibt an ihrer Stelle in der Liste.
- **Sprachwechsel wirkt auch auf offene Treffer:** Die bereits angezeigte Trefferliste wird beim Umschalten mit übersetzt.
- **Online-Seitenangabe einheitlich:** Trefferliste und Leser verwenden garantiert dieselbe Seitenbeschriftung.

### Oberfläche
- **Sicherheitsabfragen im App-Stil** statt der technischen System-Dialoge.
- **„Was ist neu"** wird sauber formatiert angezeigt (keine sichtbaren Formatierungszeichen).
- **Lange Suchbegriffe** brechen um, statt das Fenster zu sprengen.
- **Online-Suche** blendet Bedienelemente aus, die dort nicht wirken (Ausschluss, ODER-Gruppe); Online-Treffer zeigen ihre Herkunft.
- **Autorennamen mit „؛"** hinterlassen keine leeren Autoren-Einträge mehr.
- **Fenstergröße und -position** werden gemerkt.

<!--ar-->
## AICP Research 1.3.6

تعالج هذه النسخة نتائج اختبار موسّع – خاصةً في المشاركة الآمنة للكتب، وأرقام الصفحات القابلة للاقتباس، والقراءة الموثوقة.

### الأمان والبيانات
- **تصدير التحديد يشارك التحديد فقط:** عند تصدير كتب مختارة كان الملف يحتوي عن طريق الخطأ على **كامل** المكتبة وكل الإشارات المرجعية وبيانات شخصية (بما فيها بيانات الدخول المحفوظة للخادم). الآن يحتوي التصدير على الكتب المختارة وإشاراتها فقط – لا شيء غير ذلك، وحجم الملف أصغر تبعًا لذلك.

### قراءة موثوقة وأرقام الصفحات
- **الكتب القديمة قابلة لإعادة القراءة:** الكتب التي أُضيفت قبل إعادة تسمية التطبيق لم تعد تُقرأ من جديد أو تُفتح في أصلها («تعذّر العثور على الملف الأصلي»). يعثر التطبيق الآن على الملفات تلقائيًا.
- **ملفات النص موسومة بصدق:** ملف `.txt` لا يملك صفحات مطبوعة، فتُوسم صفحاته الآن بـ**«تقريبي»** بدل وسمها خطأً كقابلة للاقتباس.
- **اكتشاف الأصول التالفة:** الصفحات التي تعطي طبقة نص مشوّشة تُكتشف الآن وتُقرأ عبر التعرّف الضوئي – بدل إدخالها غير صالحة إلى المكتبة.
- **الإبلاغ عن المستندات الفارغة** بدل إدخالها بصمت بلا محتوى.
- **رسائل مفهومة:** الملفات التالفة أو الفارغة أو المحمية بكلمة مرور تعطي الآن رسائل واضحة بالعربية أو الألمانية بدل رسائل تقنية إنجليزية.

### القارئ والبحث
- **رقم الصفحة الصحيح فورًا:** بعد النقر على نتيجة كان القارئ يعرض لوهلة رقمًا أقل بواحد. الآن يظهر الرقم الصحيح فورًا في الأعلى.
- **«إعادة القراءة» أكثر متانة:** النقر المتكرر لم يعد يؤدي إلى قارئ فارغ لا ينتهي تحميله؛ ويبقى الصف في مكانه في القائمة.
- **تبديل اللغة يشمل النتائج المفتوحة:** تُترجم قائمة النتائج المعروضة عند التبديل.
- **توحيد رقم الصفحة على الإنترنت:** تستخدم قائمة النتائج والقارئ الوسم نفسه للصفحة.

### الواجهة
- **رسائل التأكيد بنمط التطبيق** بدل نوافذ النظام التقنية.
- **«الجديد»** يُعرض منسّقًا بشكل نظيف (بلا رموز تنسيق ظاهرة).
- **كلمات البحث الطويلة** تلتف بدل تجاوز حدود النافذة.
- **البحث عبر الإنترنت** يخفي العناصر غير الفعّالة هناك (الاستبعاد، مجموعة «أو»)؛ وتُظهر النتائج مصدرها.
- **أسماء المؤلفين التي تحوي «؛»** لم تعد تترك مؤلفين فارغين.
- **حجم النافذة وموضعها** يُحفظان.
