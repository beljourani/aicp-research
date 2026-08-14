## AICP Research 1.3.9

### Fehler nachvollziehbar machen
- **Der echte Grund wird sichtbar – und protokolliert:** Geht beim Einlesen etwas schief, zeigt die App jetzt den genauen technischen Grund samt Stelle und schreibt alles in eine **Protokolldatei** im Datenordner (mit Zeitstempeln). Bisher verschwanden solche Meldungen auf Windows spurlos, weil das Programm ohne Konsole läuft – der Grund war auf dem Gerät gar nicht zu bekommen.
- **„Fehlerbericht kopieren" und „Protokoll anzeigen":** Jede Fehlerzeile hat jetzt Knöpfe, um den Fehler mit einem Klick zu kopieren oder das Protokoll zu öffnen. Damit lässt sich ein Problem exakt melden, statt es zu beschreiben.
- **„Kein Text gefunden" erklärt sich jetzt:** Bei einer Datei ohne erkannten Text nennt die App Seiten, Zeichen, Engine und Dateigröße – so ist unterscheidbar, ob die Datei gar nicht geöffnet werden konnte oder ob es ein Scan ohne greifende Texterkennung ist.
- **Behoben:** Nach einem Sprachwechsel blieb eine bereits stehende Fehlermeldung in der alten Sprache; und der technische Grund wurde in der arabischen Ansicht verdreht dargestellt. Beides ist korrigiert.

<!--ar-->
## AICP Research 1.3.9

### جعل الأخطاء قابلة للتتبّع
- **يظهر السبب الحقيقي – ويُسجّل:** عند فشل القراءة يعرض التطبيق الآن السبب التقني الدقيق مع موضعه، ويكتب كل شيء في **ملف سجلّ** داخل مجلد البيانات (بطوابع زمنية). سابقًا كانت هذه الرسائل تختفي على ويندوز بلا أثر لأن البرنامج يعمل دون نافذة طرفية – فلم يكن السبب متاحًا على الجهاز إطلاقًا.
- **«نسخ تقرير الخطأ» و«عرض السجلّ»:** لكل سطر خطأ الآن زران لنسخ الخطأ بنقرة واحدة أو فتح السجلّ. هكذا يمكن الإبلاغ عن المشكلة بدقة بدل وصفها.
- **«لا يوجد نص» صار مفهومًا:** عند ملف دون نص مكتشف يذكر التطبيق عدد الصفحات والأحرف والمحرّك وحجم الملف – فيتّضح إن كان الملف تعذّر فتحه أصلًا أم أنه مسح ضوئي دون تعرّف نصّي فعّال.
- **إصلاحات:** بعد تبديل اللغة كانت رسالة الخطأ القائمة تبقى باللغة القديمة؛ وكان السبب التقني يظهر معكوسًا في الواجهة العربية. صُحّح الأمران.
