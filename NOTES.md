## AICP Research 1.3.7

Diese Version bringt die Suchfilter der Online-Suche zurück. UND, ODER-Gruppen und Ausschluss wirken dort jetzt genau so wie in der eigenen Bibliothek.

### Online-Suche sucht wie die eigene Bibliothek
- **ODER-Gruppen und Ausschluss sind zurück:** In der Online-Suche fehlten der Knopf für eine zweite ODER-Gruppe und das rote Ausschlussfeld. Beides ist wieder da – und wirkt auch wirklich. Bisher wurden mehrere Gruppen im Hintergrund zu einer einzigen UND-Verknüpfung zusammengezogen und Ausschlüsse verworfen, ohne dass es sichtbar war.
- **Dieselbe Logik wie offline:** Online und offline benutzen jetzt nachweislich denselben Suchweg. Eine Anfrage liefert in beiden Quellen dieselben Fundstellen, auch mit mehreren Gruppen und Ausschlüssen gleichzeitig.
- **Suche im Buch:** Auch beim Lesen eines Online-Buches wirken ODER-Gruppe und Ausschluss. Dort standen die Bedienelemente zwar, taten aber nichts.
- **Ausschluss mehrerer Wörter:** Schließt man eine Wortfolge wie „دار الكتب" aus, wird nur noch genau diese Wortfolge entfernt. Bisher flog jede Stelle mit dem ersten Wort heraus – auch dort, wo es um etwas anderes ging. Das gilt für beide Quellen.
- **Klare Rückmeldung:** Eine Suche, die nur aus Ausschlüssen besteht, sagt jetzt, dass ein Suchbegriff fehlt, statt wortlos nichts zu liefern.

### Behoben
- **Verbindung zum Online-Server auf dem Mac:** Je nach Python-Installation fehlte der App der Zertifikatsspeicher, sodass jede Verbindung mit einer Zertifikatsmeldung scheiterte. Die App bringt den Speicher jetzt selbst mit.
- **Ehrliche Verbindungsanzeige:** Neben der Quelle stand „verbunden", sobald Adresse und Token hinterlegt waren – auch wenn der Server gar nicht antwortete. Jetzt steht dort „nicht erreichbar", solange kein Zugriff gelingt.

<!--ar-->
## AICP Research 1.3.7

تُعيد هذه النسخة مرشّحات البحث إلى البحث عبر الإنترنت. «و» ومجموعات «أو» والاستبعاد تعمل هناك الآن تمامًا كما في مكتبتك الخاصة.

### البحث عبر الإنترنت يبحث كمكتبتك
- **عودة مجموعات «أو» والاستبعاد:** كان زر إضافة مجموعة «أو» وحقل الاستبعاد الأحمر غائبَين في البحث عبر الإنترنت. عادا الآن – ويعملان فعلًا. سابقًا كانت المجموعات المتعددة تُدمج خلف الكواليس في رابط «و» واحد وتُهمل الاستبعادات دون أن يظهر ذلك.
- **المنطق نفسه كما دون اتصال:** يستخدم البحثان الآن المسار نفسه فعليًا. الطلب الواحد يعطي المواضع نفسها في المصدرين، حتى مع عدة مجموعات واستبعادات معًا.
- **البحث داخل الكتاب:** تعمل مجموعة «أو» والاستبعاد أيضًا أثناء قراءة كتاب من الإنترنت. كانت العناصر موجودة هناك لكنها بلا أثر.
- **استبعاد عدة كلمات:** عند استبعاد عبارة مثل «دار الكتب» تُحذف هذه العبارة وحدها. سابقًا كان يسقط كل موضع فيه الكلمة الأولى – حتى حيث لا علاقة له بالمقصود. وهذا يسري على المصدرين.
- **رسالة واضحة:** البحث المكوّن من استبعادات فقط يخبرك الآن بأن كلمة البحث ناقصة، بدل ألا يعطي شيئًا بصمت.

### إصلاحات
- **الاتصال بالخادم على نظام ماك:** بحسب تثبيت بايثون كان مخزن الشهادات ناقصًا، فيفشل كل اتصال برسالة شهادة. صار التطبيق يحمل المخزن معه.
- **مؤشر اتصال صادق:** كان يظهر «متصل» بمجرد حفظ العنوان والرمز، حتى إن لم يستجب الخادم. الآن يظهر «تعذّر الوصول» ما دام الوصول غير ممكن.
