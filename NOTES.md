## AICP Research 1.4

Diese Version ist eine Grundsanierung. Die App wurde vollständig daraufhin durchgesehen, was auf **fremden Geräten** schiefgehen kann – und nicht nur gemeldet, sondern behoben. Dazu kommt eine automatische Prüfung, die vor jeder Veröffentlichung durchlaufen muss.

### Nichts geht mehr verloren
- **„Neu einlesen" kann ein Buch nicht mehr vernichten.** Bisher wurde das Buch zuerst gelöscht und erst danach neu eingelesen – schlug das Einlesen fehl, war es unwiederbringlich weg. Jetzt wird erst gelesen und das alte erst danach ersetzt.
- **Keine Geistertreffer mehr** nach dem Neu-Einlesen (Treffer, deren Text das gesuchte Wort gar nicht enthielt).
- **Ein Update kann die App nicht mehr unbrauchbar machen.** Brach ein Download unbemerkt ab, startete eine beschädigte Installation und die App schloss sich – und kam nicht wieder. Jetzt wird die Vollständigkeit geprüft, und die App beendet sich nur, wenn die Installation wirklich läuft.

### Dokumente werden zuverlässig gelesen – auf jedem Gerät
- **PDFs lassen sich immer lesen.** Die App bringt jetzt einen zweiten, unabhängigen Weg mit. Falls die eingebaute PDF-Komponente auf einem Rechner nicht startet (genau das führte auf einem Gerät dazu, dass **jede** PDF abgelehnt wurde), übernimmt der Ersatzweg – mit unveränderten Seitenzahlen.
- **Textdateien in jeder Kodierung.** Bisher wurde nur eine einzige Schreibweise erwartet: Dateien aus dem Windows-Editor wurden zu Zeichensalat, deutsche Umlaute gingen verloren, arabische Textdateien galten als leer. Jetzt werden alle üblichen Kodierungen erkannt.
- **Word-Dokumente mit Tabellen** verlieren ihren Inhalt nicht mehr; Kopf- und Fußzeilen kommen mit.
- **Ältere und fremde Formate** (.doc, .rtf, .odt) werden angenommen. Fehlt der nötige Konverter, sagt die App im Klartext, was zu tun ist – statt die Datei kommentarlos abzulehnen.
- **Ein passwortgeschütztes Word-Dokument blockiert nicht mehr das ganze Programm** (bisher konnte eine einzige solche Datei das Einlesen dauerhaft lahmlegen).
- **Eine beschädigte Seite kostet nur diese Seite**, nicht mehr das ganze Buch.

### Suche: Umlaute und weitere Sprachen
- **„Müller", „Öl", „Straße" werden jetzt gefunden.** Im Suchindex zerfielen Wörter mit Umlauten bisher in Bruchstücke – deutsche Begriffe waren dadurch nur eingeschränkt auffindbar.
- **Russische, chinesische, hebräische und persische Bücher** werden korrekt aufgenommen. Bisher wurden sie beim Einlesen als „kein Text gefunden" verworfen, obwohl sie einwandfrei gelesen waren.
- Der Suchindex wird dafür beim ersten Start **einmalig neu aufgebaut**; Bücher, Lesezeichen und Originaldateien bleiben unangetastet.

### Seitenzahlen bleiben verlässlich
- **Die Schriften für die Word-Umwandlung werden jetzt mitgeliefert.** Bisher wurden sie aus dem Internet geladen – ohne Verbindung entstanden dadurch andere Seitenumbrüche als auf einem Rechner mit Internet.
- **Texterkennung rät nicht mehr die Sprache.** Bisher wurde im Zweifel Arabisch angenommen, wodurch deutsche Scans unbrauchbar erkannt wurden.
- **Hinweise werden angezeigt**, statt verworfen zu werden: etwa wenn Seitenzahlen nur geschätzt sind oder die Textebene eines PDFs beschädigt war.

### Die App startet – oder sagt, warum
- **Fehlt Windows die Anzeige-Komponente (WebView2)**, erklärt die App das jetzt und der Installer bringt sie mit. Bisher erschien ein **weißes Fenster ohne jede Meldung**.
- **Auf älteren Rechnern** schaltet sich die Bedeutungssuche selbst ab, statt das Programm abstürzen zu lassen; Wort- und Wurzelsuche laufen unverändert weiter.
- **Neue Systemprüfung** in der Seitenleiste: sie zeigt für jedes Gerät, welche Komponenten vorhanden sind – und lässt sich mit einem Klick kopieren.
- Ist der übliche Datenordner gesperrt, weicht die App aus, statt gar nicht zu starten.

### Weniger Ballast
- Hochgeladene Dateien werden beim Löschen eines Buches mit entfernt (bisher blieben sie für immer liegen).
- Sehr große Dateien werden beim Hinzufügen nicht mehr komplett in den Arbeitsspeicher geladen.

<!--ar-->
## AICP Research 1.4

هذه النسخة إصلاح شامل. رُوجع التطبيق بالكامل بحثًا عمّا يمكن أن يفشل على **أجهزة أخرى** – ولم يُكتفَ بالإبلاغ بل تمّ الإصلاح. ويُضاف إلى ذلك فحص آلي يجب أن ينجح قبل كل إصدار.

### لا شيء يُفقد بعد الآن
- **«إعادة القراءة» لم تعد قادرة على إتلاف كتاب.** سابقًا كان الكتاب يُحذف أولًا ثم يُقرأ من جديد – وإذا فشلت القراءة ضاع نهائيًا. الآن تتم القراءة أولًا ولا يُستبدل القديم إلا بعد نجاحها.
- **لا نتائج شبحية** بعد إعادة القراءة (نتائج لا يحتوي نصها الكلمة المطلوبة أصلًا).
- **لم يعد التحديث قادرًا على تعطيل التطبيق.** إذا انقطع التنزيل دون إشعار، كان يبدأ تثبيت تالف ويُغلق التطبيق – ولا يعود. الآن يُتحقق من اكتمال الملف، ولا يُغلق التطبيق إلا إذا كان التثبيت يعمل فعلًا.

### قراءة موثوقة للمستندات – على كل جهاز
- **ملفات PDF تُقرأ دائمًا.** يحمل التطبيق الآن مسارًا ثانيًا مستقلًا. فإذا تعذّر تشغيل مكوّن PDF المدمج على جهاز ما (وهو ما جعل **كل** ملف PDF يُرفض على أحد الأجهزة)، يتولّى المسار البديل – بأرقام صفحات دون تغيير.
- **ملفات نصية بأي ترميز.** سابقًا كان يُتوقّع ترميز واحد فقط: ملفات محرّر ويندوز تتحوّل إلى رموز مشوّشة، والحروف الألمانية الخاصة تضيع، والملفات العربية تُعدّ فارغة. الآن تُكتشف جميع الترميزات الشائعة.
- **مستندات وورد ذات الجداول** لم تعد تفقد محتواها؛ وتُقرأ الرؤوس والتذييلات.
- **الصيغ الأقدم والأخرى** (‎.doc، .rtf، .odt‎) مقبولة. وإذا غاب المحوّل اللازم يوضّح التطبيق ما ينبغي فعله بدل رفض الملف بصمت.
- **مستند وورد محمي بكلمة مرور لم يعد يعطّل البرنامج كله** (سابقًا كان ملف واحد كافيًا لتعطيل القراءة نهائيًا).
- **الصفحة التالفة تُكلّف تلك الصفحة فقط**، لا الكتاب بأكمله.

### البحث: الحروف الخاصة ولغات إضافية
- **«Müller» و«Öl» و«Straße» تُوجد الآن.** كانت الكلمات ذات الحروف الألمانية الخاصة تتفتّت في الفهرس، فتصعب إيجادها.
- **الكتب الروسية والصينية والعبرية والفارسية** تُضاف بشكل صحيح. سابقًا كانت تُرفض بوصفها «لا يوجد نص» رغم قراءتها سليمة.
- لذلك يُعاد بناء فهرس البحث **مرة واحدة** عند أول تشغيل؛ وتبقى الكتب والإشارات المرجعية والملفات الأصلية كما هي.

### أرقام الصفحات تبقى موثوقة
- **خطوط تحويل وورد صارت مضمّنة.** سابقًا كانت تُحمَّل من الإنترنت – ودونه تنشأ فواصل صفحات مختلفة عن جهاز متصل.
- **التعرّف الضوئي لم يعد يخمّن اللغة.** سابقًا كانت العربية تُفترض عند الشك، فتُقرأ المسوحات الألمانية بشكل غير صالح.
- **تُعرض الملاحظات** بدل إهمالها: مثل كون أرقام الصفحات تقديرية أو كون طبقة نص الملف تالفة.

### التطبيق يبدأ – أو يوضّح السبب
- **إذا غاب مكوّن العرض في ويندوز (WebView2)** يشرح التطبيق ذلك، ويحمله المثبّت معه. سابقًا كانت تظهر **نافذة بيضاء دون أي رسالة**.
- **على الأجهزة الأقدم** يعطّل البحث الدلالي نفسه بدل أن يُسقط البرنامج؛ ويستمر البحث بالكلمة والجذر كما هو.
- **فحص نظام جديد** في الشريط الجانبي: يعرض لكل جهاز المكوّنات المتوفّرة، ويمكن نسخه بنقرة.
- إذا كان مجلد البيانات المعتاد محجوبًا، يتحوّل التطبيق إلى مكان بديل بدل ألا يبدأ.

### حِمل أقل
- تُحذف الملفات المرفوعة مع حذف الكتاب (سابقًا كانت تبقى إلى الأبد).
- لم تعد الملفات الكبيرة تُحمَّل بالكامل في الذاكرة عند الإضافة.
