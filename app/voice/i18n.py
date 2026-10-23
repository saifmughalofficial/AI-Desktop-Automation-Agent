"""Voice languages: offline speech models, voices, native command keywords and
localized replies. Native phrases are mapped to the assistant's canonical
English commands (plain substring matching — speech is never executed)."""
from __future__ import annotations

import re

# code: name, Vosk model, approx MB, espeak-ng voice, full (keywords + replies) support, right-to-left
LANGS: dict[str, dict] = {
    "en": dict(name="English (US) — fast + command-tuned (recommended)", native="English",
               model="vosk-model-small-en-us-0.15", mb=39, voice="en-us"),
    "en-hq": dict(name="English (US) — large model (slower PCs may lag)", native="English",
                  model="vosk-model-en-us-0.22-lgraph", mb=124, voice="en-us"),
    "en-in": dict(name="English (India/Pakistan)", native="English", model="vosk-model-small-en-in-0.4", mb=35, voice="en"),
    "ur": dict(name="Urdu", native="اردو", model="vosk-model-small-hi-0.22", mb=42, voice="ur", rtl=True),
    "hi": dict(name="Hindi", native="हिन्दी", model="vosk-model-small-hi-0.22", mb=42, voice="hi"),
    "ar": dict(name="Arabic", native="العربية", model="vosk-model-ar-mgb2-0.4", mb=317, voice="ar", rtl=True),
    "fa": dict(name="Persian", native="فارسی", model="vosk-model-small-fa-0.42", mb=50, voice="fa", rtl=True),
    "tr": dict(name="Turkish", native="Türkçe", model="vosk-model-small-tr-0.3", mb=35, voice="tr"),
    "fr": dict(name="French", native="Français", model="vosk-model-small-fr-0.22", mb=40, voice="fr"),
    "es": dict(name="Spanish", native="Español", model="vosk-model-small-es-0.42", mb=37, voice="es"),
    "de": dict(name="German", native="Deutsch", model="vosk-model-small-de-0.15", mb=44, voice="de"),
    "it": dict(name="Italian", native="Italiano", model="vosk-model-small-it-0.22", mb=47, voice="it"),
    "pt": dict(name="Portuguese", native="Português", model="vosk-model-small-pt-0.3", mb=30, voice="pt-br"),
    "ru": dict(name="Russian", native="Русский", model="vosk-model-small-ru-0.22", mb=44, voice="ru"),
    "zh": dict(name="Chinese (Mandarin)", native="中文", model="vosk-model-small-cn-0.22", mb=41, voice="cmn"),
    "ja": dict(name="Japanese", native="日本語", model="vosk-model-small-ja-0.22", mb=47, voice="ja"),
    "ko": dict(name="Korean", native="한국어", model="vosk-model-small-ko-0.22", mb=82, voice="ko"),
    "nl": dict(name="Dutch", native="Nederlands", model="vosk-model-small-nl-0.22", mb=38, voice="nl"),
    "uk": dict(name="Ukrainian", native="Українська", model="vosk-model-small-uk-v3-small", mb=137, voice="uk"),
    "vi": dict(name="Vietnamese", native="Tiếng Việt", model="vosk-model-small-vn-0.4", mb=32, voice="vi"),
    "gu": dict(name="Gujarati", native="ગુજરાતી", model="vosk-model-small-gu-0.42", mb=103, voice="gu"),
    "te": dict(name="Telugu", native="తెలుగు", model="vosk-model-small-te-0.42", mb=57, voice="te"),
}

# Canonical commands, checked in this order (specific before general).
CANON = ["cancel shutdown", "shut down the computer", "restart the computer", "lock the screen", "volume up",
         "volume down", "mute", "next track", "previous track", "play", "stop", "top processes", "cpu usage",
         "memory usage", "disk space", "battery", "uptime", "network", "system status", "what time is it",
         "what is the date", "open notepad", "open calculator", "open paint", "go to history", "go to settings",
         "go to system", "go to files", "go to command center", "help", "thank you", "hello"]

KW: dict[str, dict[str, list[str]]] = {
    "ur": {  # Urdu script + Roman Urdu
        "cancel shutdown": ["شٹ ڈاؤن منسوخ", "shutdown cancel", "band karna cancel"],
        "shut down the computer": ["کمپیوٹر بند", "شٹ ڈاؤن", "computer band", "pc band", "shutdown kar"],
        "restart the computer": ["ری اسٹارٹ", "دوبارہ شروع", "restart kar", "dobara shuru"],
        "lock the screen": ["اسکرین لاک", "لاک کر", "screen lock", "lock kar"],
        "volume up": ["آواز بڑھا", "آواز اونچی", "awaz barha", "awaz tez", "volume barha", "volume up"],
        "volume down": ["آواز کم", "آواز دھیمی", "awaz kam", "awaz halki", "volume kam"],
        "mute": ["آواز بند", "خاموش", "awaz band", "mute kar"],
        "next track": ["اگلا گانا", "agla gana"], "previous track": ["پچھلا گانا", "pichla gana"],
        "play": ["گانا چلا", "چلاؤ", "gana chala", "play kar"],
        "stop": ["رک جاؤ", "روکو", "ruk jao", "roko", "ruko"],
        "top processes": ["پروسیس", "کون سا پروگرام", "process dikha", "kon sa program"],
        "cpu usage": ["سی پی یو", "پروسیسر", "cpu", "processor"],
        "memory usage": ["میموری", "ریم", "memory", "ram"],
        "disk space": ["ڈسک", "اسٹوریج", "جگہ", "disk", "storage", "jagah"],
        "battery": ["بیٹری", "چارج", "battery", "charge"],
        "uptime": ["کب سے چل", "kab se chal", "uptime"],
        "network": ["انٹرنیٹ", "نیٹ ورک", "وائی فائی", "internet", "network", "wifi"],
        "system status": ["سسٹم", "کمپیوٹر کی حالت", "system", "computer ki halat", "status"],
        "what time is it": ["وقت", "ٹائم", "کتنے بجے", "waqt", "time kya", "kitne baje", "time"],
        "what is the date": ["تاریخ", "آج کون سا دن", "tareekh", "tarikh", "date"],
        "open notepad": ["نوٹ پیڈ", "notepad"], "open calculator": ["کیلکولیٹر", "calculator"],
        "open paint": ["پینٹ", "paint"],
        "go to history": ["ہسٹری", "تاریخچہ", "history"], "go to settings": ["سیٹنگ", "ترتیبات", "setting"],
        "go to files": ["فائل", "file"], "help": ["مدد", "کیا کر سکتے", "madad", "help"],
        "thank you": ["شکریہ", "shukriya", "shukria"],
        "hello": ["سلام", "ہیلو", "آداب", "salam", "hello", "assalam"],
    },
    "hi": {
        "cancel shutdown": ["शटडाउन रद्द", "शट डाउन कैंसल"],
        "shut down the computer": ["कंप्यूटर बंद", "शटडाउन", "शट डाउन", "पीसी बंद"],
        "restart the computer": ["रीस्टार्ट", "री स्टार्ट", "दोबारा शुरू", "फिर से शुरू"],
        "lock the screen": ["स्क्रीन लॉक", "लॉक कर", "लॉक करो"],
        "volume up": ["आवाज़ बढ़ा", "आवाज बढ़ा", "आवाज़ तेज़", "आवाज तेज", "वॉल्यूम बढ़ा"],
        "volume down": ["आवाज़ कम", "आवाज कम", "आवाज़ धीमी", "वॉल्यूम कम"],
        "mute": ["आवाज़ बंद", "आवाज बंद", "म्यूट"], "next track": ["अगला गाना"], "previous track": ["पिछला गाना"],
        "play": ["गाना चला", "चलाओ"], "stop": ["रुक जाओ", "रोको", "रुको"],
        "top processes": ["प्रोसेस", "कौन सा प्रोग्राम"], "cpu usage": ["सीपीयू", "सी पी यू", "प्रोसेसर"],
        "memory usage": ["मेमोरी", "रैम"], "disk space": ["डिस्क", "स्टोरेज", "जगह"],
        "battery": ["बैटरी", "चार्ज"], "uptime": ["कब से चल"], "network": ["इंटरनेट", "नेटवर्क", "वाईफाई"],
        "system status": ["सिस्टम", "कंप्यूटर की हालत", "स्टेटस"],
        "what time is it": ["समय", "वक़्त", "वक्त", "टाइम", "कितने बजे"], "what is the date": ["तारीख", "आज कौन सा दिन", "दिनांक"],
        "open notepad": ["नोटपैड", "नोट पैड"], "open calculator": ["कैलकुलेटर"], "open paint": ["पेंट"],
        "go to history": ["हिस्ट्री", "इतिहास"], "go to settings": ["सेटिंग"], "go to files": ["फ़ाइल", "फाइल"],
        "help": ["मदद", "सहायता"], "thank you": ["धन्यवाद", "शुक्रिया"],
        "hello": ["नमस्ते", "सलाम", "हेलो", "हैलो"],
    },
    "ar": {
        "cancel shutdown": ["إلغاء الإيقاف"], "shut down the computer": ["أطفئ", "اطفئ", "إيقاف التشغيل", "اغلق الحاسوب"],
        "restart the computer": ["إعادة التشغيل", "اعادة التشغيل"], "lock the screen": ["اقفل الشاشة", "قفل الشاشة"],
        "volume up": ["ارفع الصوت", "رفع الصوت"], "volume down": ["اخفض الصوت", "خفض الصوت"], "mute": ["كتم الصوت", "اكتم"],
        "next track": ["الأغنية التالية"], "previous track": ["الأغنية السابقة"], "play": ["تشغيل الموسيقى", "شغل"],
        "stop": ["توقف"], "top processes": ["العمليات"], "cpu usage": ["المعالج"], "memory usage": ["الذاكرة", "الرام"],
        "disk space": ["القرص", "التخزين", "المساحة"], "battery": ["البطارية", "الشحن"], "uptime": ["مدة التشغيل"],
        "network": ["الإنترنت", "الشبكة", "واي فاي"], "system status": ["النظام", "حالة الجهاز"],
        "what time is it": ["الساعة", "الوقت"], "what is the date": ["التاريخ", "اليوم"], "open notepad": ["المفكرة", "نوتباد"],
        "open calculator": ["الآلة الحاسبة", "الحاسبة"], "open paint": ["الرسام", "بينت"], "go to history": ["السجل"],
        "go to settings": ["الإعدادات"], "go to files": ["الملفات"], "help": ["مساعدة", "ساعدني"],
        "thank you": ["شكرا", "شكراً"], "hello": ["مرحبا", "السلام عليكم", "أهلا"],
    },
    "fa": {
        "shut down the computer": ["خاموش کن", "کامپیوتر را خاموش"], "restart the computer": ["ری استارت", "راه اندازی مجدد"],
        "lock the screen": ["قفل صفحه"], "volume up": ["صدا را زیاد", "صدا بلند"], "volume down": ["صدا را کم"],
        "mute": ["بی صدا", "صدا را قطع"], "stop": ["توقف", "بایست"], "cpu usage": ["پردازنده"], "memory usage": ["حافظه", "رم"],
        "disk space": ["دیسک", "فضای"], "battery": ["باتری"], "network": ["اینترنت", "شبکه"], "system status": ["سیستم", "وضعیت"],
        "what time is it": ["ساعت", "زمان"], "what is the date": ["تاریخ", "امروز"], "open notepad": ["نوت پد", "دفترچه"],
        "open calculator": ["ماشین حساب"], "help": ["کمک", "راهنما"], "thank you": ["ممنون", "مرسی", "متشکرم"],
        "hello": ["سلام", "درود"],
    },
    "tr": {
        "cancel shutdown": ["kapatmayı iptal"], "shut down the computer": ["bilgisayarı kapat"],
        "restart the computer": ["yeniden başlat"], "lock the screen": ["ekranı kilitle", "kilitle"],
        "volume up": ["sesi aç", "sesi yükselt", "ses aç"], "volume down": ["sesi kıs", "sesi azalt"], "mute": ["sessiz", "sesi kapat"],
        "next track": ["sonraki şarkı"], "previous track": ["önceki şarkı"], "play": ["müziği çal", "oynat"], "stop": ["dur", "durdur"],
        "top processes": ["işlemler"], "cpu usage": ["işlemci", "cpu"], "memory usage": ["bellek", "ram"],
        "disk space": ["disk", "depolama"], "battery": ["pil", "batarya", "şarj"], "uptime": ["çalışma süresi"],
        "network": ["internet", "ağ", "wifi"], "system status": ["sistem", "durum"], "what time is it": ["saat kaç", "saat"],
        "what is the date": ["tarih", "bugün"], "open notepad": ["not defteri"], "open calculator": ["hesap makinesi"],
        "open paint": ["paint"], "go to history": ["geçmiş"], "go to settings": ["ayarlar"], "go to files": ["dosyalar"],
        "help": ["yardım"], "thank you": ["teşekkür", "sağ ol"], "hello": ["merhaba", "selam"],
    },
    "fr": {
        "cancel shutdown": ["annule l'arrêt", "annuler l'arrêt"], "shut down the computer": ["éteins", "éteindre", "arrête l'ordinateur"],
        "restart the computer": ["redémarre", "redémarrer"], "lock the screen": ["verrouille", "verrouiller"],
        "volume up": ["monte le son", "augmente le volume", "plus fort"], "volume down": ["baisse le son", "baisse le volume", "moins fort"],
        "mute": ["coupe le son", "muet"], "next track": ["chanson suivante", "piste suivante"],
        "previous track": ["chanson précédente", "piste précédente"], "play": ["joue la musique", "lecture"],
        "stop": ["arrête tout", "stop", "arrête"], "top processes": ["processus"], "cpu usage": ["processeur", "cpu"],
        "memory usage": ["mémoire", "ram"], "disk space": ["disque", "stockage", "espace"], "battery": ["batterie"],
        "uptime": ["depuis quand"], "network": ["internet", "réseau", "wifi"], "system status": ["système", "état"],
        "what time is it": ["quelle heure", "l'heure"], "what is the date": ["date", "quel jour"],
        "open notepad": ["bloc-notes", "bloc notes", "notepad"], "open calculator": ["calculatrice"], "open paint": ["paint"],
        "go to history": ["historique"], "go to settings": ["paramètres", "réglages"], "go to files": ["fichiers"],
        "help": ["aide"], "thank you": ["merci"], "hello": ["bonjour", "salut"],
    },
    "es": {
        "cancel shutdown": ["cancela el apagado"], "shut down the computer": ["apaga", "apagar"], "restart the computer": ["reinicia", "reiniciar"],
        "lock the screen": ["bloquea", "bloquear"], "volume up": ["sube el volumen", "más volumen"],
        "volume down": ["baja el volumen", "menos volumen"], "mute": ["silencio", "silenciar", "quita el sonido"],
        "next track": ["siguiente canción"], "previous track": ["canción anterior"], "play": ["reproduce", "pon música"],
        "stop": ["detente", "detener"], "top processes": ["procesos"], "cpu usage": ["procesador", "cpu"],
        "memory usage": ["memoria", "ram"], "disk space": ["disco", "almacenamiento", "espacio"], "battery": ["batería"],
        "uptime": ["tiempo encendido"], "network": ["internet", "red", "wifi"], "system status": ["sistema", "estado"],
        "what time is it": ["qué hora", "la hora"], "what is the date": ["fecha", "qué día"], "open notepad": ["bloc de notas", "notepad"],
        "open calculator": ["calculadora"], "open paint": ["paint"], "go to history": ["historial"],
        "go to settings": ["configuración", "ajustes"], "go to files": ["archivos"], "help": ["ayuda"],
        "thank you": ["gracias"], "hello": ["hola", "buenos días"],
    },
    "de": {
        "cancel shutdown": ["herunterfahren abbrechen"], "shut down the computer": ["herunterfahren", "ausschalten"],
        "restart the computer": ["neu starten", "neustart"], "lock the screen": ["sperren", "bildschirm sperren"],
        "volume up": ["lauter", "lautstärke erhöhen"], "volume down": ["leiser", "lautstärke verringern"], "mute": ["stumm", "ton aus"],
        "next track": ["nächstes lied", "nächster titel"], "previous track": ["vorheriges lied", "vorheriger titel"],
        "play": ["musik abspielen", "abspielen"], "stop": ["stopp", "anhalten"], "top processes": ["prozesse"],
        "cpu usage": ["prozessor", "cpu"], "memory usage": ["arbeitsspeicher", "speicher", "ram"], "disk space": ["festplatte", "speicherplatz"],
        "battery": ["akku", "batterie"], "uptime": ["laufzeit"], "network": ["internet", "netzwerk", "wlan"],
        "system status": ["system", "status"], "what time is it": ["wie spät", "uhrzeit"], "what is the date": ["datum", "welcher tag"],
        "open notepad": ["editor", "notepad"], "open calculator": ["rechner"], "open paint": ["paint"], "go to history": ["verlauf"],
        "go to settings": ["einstellungen"], "go to files": ["dateien"], "help": ["hilfe"], "thank you": ["danke"],
        "hello": ["hallo", "guten tag"],
    },
    "it": {
        "shut down the computer": ["spegni"], "restart the computer": ["riavvia"], "lock the screen": ["blocca"],
        "volume up": ["alza il volume"], "volume down": ["abbassa il volume"], "mute": ["muto", "silenzia"], "stop": ["fermati", "ferma"],
        "cpu usage": ["processore", "cpu"], "memory usage": ["memoria", "ram"], "disk space": ["disco", "spazio"],
        "battery": ["batteria"], "network": ["internet", "rete"], "system status": ["sistema", "stato"],
        "what time is it": ["che ore", "l'ora"], "what is the date": ["data", "che giorno"], "open notepad": ["blocco note", "notepad"],
        "open calculator": ["calcolatrice"], "help": ["aiuto"], "thank you": ["grazie"], "hello": ["ciao", "buongiorno"],
    },
    "pt": {
        "shut down the computer": ["desligar", "desliga"], "restart the computer": ["reiniciar", "reinicia"],
        "lock the screen": ["bloquear", "bloqueia"], "volume up": ["aumentar o volume", "aumenta o volume"],
        "volume down": ["diminuir o volume", "abaixa o volume"], "mute": ["mudo", "silenciar"], "stop": ["pare", "parar"],
        "top processes": ["processos"], "cpu usage": ["processador", "cpu"], "memory usage": ["memória", "ram"],
        "disk space": ["disco", "armazenamento", "espaço"], "battery": ["bateria"], "network": ["internet", "rede"],
        "system status": ["sistema", "estado"], "what time is it": ["que horas", "hora"], "what is the date": ["data", "que dia"],
        "open notepad": ["bloco de notas", "notepad"], "open calculator": ["calculadora"], "go to history": ["histórico"],
        "go to settings": ["configurações"], "help": ["ajuda"], "thank you": ["obrigado", "obrigada"], "hello": ["olá", "oi", "bom dia"],
    },
    "ru": {
        "cancel shutdown": ["отмени выключение"], "shut down the computer": ["выключи компьютер", "выключить компьютер"],
        "restart the computer": ["перезагрузи", "перезагрузка"], "lock the screen": ["заблокируй", "блокировка"],
        "volume up": ["громче", "увеличь громкость"], "volume down": ["тише", "уменьши громкость"], "mute": ["выключи звук", "без звука"],
        "next track": ["следующая песня", "следующий трек"], "previous track": ["предыдущая песня", "предыдущий трек"],
        "play": ["включи музыку", "играй"], "stop": ["стоп", "остановись", "останови"], "top processes": ["процессы"],
        "cpu usage": ["процессор"], "memory usage": ["памят", "оперативк"], "disk space": ["диск", "место"],
        "battery": ["батаре", "заряд"], "uptime": ["время работы"], "network": ["интернет", "сеть", "вайфай"],
        "system status": ["система", "состояние"], "what time is it": ["который час", "время"],
        "what is the date": ["дата", "какое сегодня число", "какой день"], "open notepad": ["блокнот"],
        "open calculator": ["калькулятор"], "open paint": ["паинт"], "go to history": ["история"], "go to settings": ["настройки"],
        "go to files": ["файлы"], "help": ["помощь", "помоги"], "thank you": ["спасибо"], "hello": ["привет", "здравствуй"],
    },
    "zh": {
        "cancel shutdown": ["取消关机"], "shut down the computer": ["关机", "关闭电脑"], "restart the computer": ["重启", "重新启动"],
        "lock the screen": ["锁屏", "锁定屏幕"], "volume up": ["调高音量", "大声", "音量调大"], "volume down": ["调低音量", "小声", "音量调小"],
        "mute": ["静音"], "next track": ["下一首"], "previous track": ["上一首"], "play": ["播放"], "stop": ["停止", "停下"],
        "top processes": ["进程"], "cpu usage": ["处理器", "cpu"], "memory usage": ["内存"], "disk space": ["磁盘", "硬盘", "存储"],
        "battery": ["电池", "电量"], "uptime": ["运行时间"], "network": ["网络", "无线"], "system status": ["系统", "状态"],
        "what time is it": ["几点", "时间"], "what is the date": ["日期", "几号", "星期几"], "open notepad": ["记事本"],
        "open calculator": ["计算器"], "open paint": ["画图"], "go to history": ["历史"], "go to settings": ["设置"],
        "go to files": ["文件"], "help": ["帮助"], "thank you": ["谢谢"], "hello": ["你好", "您好"],
    },
}
KW["en-in"] = {}

# Localized replies (missing keys fall back to English).
T: dict[str, dict[str, str]] = {
    "en": {
        "didnt_catch": "I didn't catch that. {help}", "hello": "Hello! I'm your desktop agent. {help}",
        "time": "It's {time}.", "date": "Today is {date}.", "thanks": "You're welcome!",
        "stop": "Emergency stop requested.", "nothing_running": "Nothing is running right now.",
        "navigate": "Opening the {page} page.",
        "agent": "Sending to the agent: “{text}”. Review the plan and approve it in the Command Center.",
        "agent_other": "I sent “{text}” to the agent. File and app tasks are understood best in English "
                       "(or with a local AI model enabled).",
        "cant": "I can't do that here. {reason}", "done": "Done. {msg}",
        "confirm_power": "Please confirm: {reason} Press Confirm to continue.",
        "confirm_kill": "Please confirm ending {name} (PID {pid}). Unsaved work in it will be lost.",
        "refuse_kill": "I won't end {name}: {reason}", "no_proc": "No running process matches “{name}”.",
        "top": "Top processes by {by}: {items}.", "cpu": "CPU usage is {v} percent.",
        "mem": "Memory usage is {v} percent, with {free} available.", "disk": "Disk: {txt}.",
        "no_battery": "No battery detected — this machine runs on mains power.",
        "battery": "Battery is at {v} percent, {state}.", "plugged": "plugged in", "on_battery": "on battery",
        "uptime": "The system has been up for {up}.", "net": "Connected interfaces: {txt}.",
        "no_net": "No active network interface with an IPv4 address was found.",
        "status": "System health score {score} out of 100. CPU {cpu} percent, memory {mem} percent, "
                  "system disk {disk} percent, up for {up}.",
        "who": "I'm the AI Desktop Automation Agent — an offline assistant that manages your system and automates "
               "files and apps with your approval.",
    },
    "ur": {
        "didnt_catch": "معاف کیجیے، میں سمجھ نہیں سکا۔ دوبارہ کہیں۔", "hello": "السلام علیکم! میں آپ کا ڈیسک ٹاپ ایجنٹ ہوں۔ آپ سسٹم کی حالت، بیٹری، وقت یا آواز کے بارے میں پوچھ سکتے ہیں۔",
        "time": "ابھی {time} ہوئے ہیں۔", "date": "آج {date} ہے۔", "thanks": "آپ کا شکریہ!", "stop": "ایمرجنسی اسٹاپ کی درخواست کر دی گئی ہے۔",
        "nothing_running": "ابھی کوئی کام نہیں چل رہا۔", "navigate": "{page} صفحہ کھول رہا ہوں۔",
        "agent": "یہ کام ایجنٹ کو بھیج دیا: “{text}”۔ کمانڈ سینٹر میں منصوبہ دیکھ کر منظوری دیں۔",
        "agent_other": "میں نے “{text}” ایجنٹ کو بھیج دیا ہے۔ فائل اور ایپ کے کام انگریزی میں بہتر سمجھے جاتے ہیں۔",
        "cant": "یہ کام یہاں نہیں ہو سکتا۔ {reason}", "done": "ہو گیا۔ {msg}",
        "confirm_power": "براہِ کرم تصدیق کریں۔ {reason} جاری رکھنے کے لیے Confirm دبائیں۔",
        "confirm_kill": "کیا آپ {name} (PID {pid}) بند کرنا چاہتے ہیں؟ اس میں محفوظ نہ کیا گیا کام ضائع ہو جائے گا۔",
        "refuse_kill": "میں {name} بند نہیں کروں گا: {reason}", "no_proc": "“{name}” نام کا کوئی پروسیس نہیں چل رہا۔",
        "top": "سب سے زیادہ استعمال کرنے والے پروگرام: {items}۔", "cpu": "سی پی یو کا استعمال {v} فیصد ہے۔",
        "mem": "میموری کا استعمال {v} فیصد ہے، اور {free} خالی ہے۔", "disk": "ڈسک: {txt}۔",
        "no_battery": "کوئی بیٹری نہیں ملی، یہ کمپیوٹر بجلی پر چل رہا ہے۔", "battery": "بیٹری {v} فیصد ہے، {state}۔",
        "plugged": "چارجر لگا ہوا ہے", "on_battery": "بیٹری پر چل رہا ہے", "uptime": "سسٹم {up} سے چل رہا ہے۔",
        "net": "منسلک نیٹ ورک: {txt}۔", "no_net": "کوئی فعال نیٹ ورک نہیں ملا۔",
        "status": "سسٹم کی صحت 100 میں سے {score}۔ سی پی یو {cpu} فیصد، میموری {mem} فیصد، ڈسک {disk} فیصد، اور سسٹم {up} سے چل رہا ہے۔",
        "who": "میں اے آئی ڈیسک ٹاپ آٹومیشن ایجنٹ ہوں، جو آپ کی اجازت سے سسٹم سنبھالتا ہے۔",
    },
    "hi": {
        "didnt_catch": "माफ़ कीजिए, मैं समझ नहीं पाया। फिर से कहिए।", "hello": "नमस्ते! मैं आपका डेस्कटॉप एजेंट हूँ। आप सिस्टम, बैटरी, समय या आवाज़ के बारे में पूछ सकते हैं।",
        "time": "अभी {time} बजे हैं।", "date": "आज {date} है।", "thanks": "आपका स्वागत है!", "stop": "इमरजेंसी स्टॉप का अनुरोध कर दिया गया है।",
        "nothing_running": "अभी कुछ नहीं चल रहा।", "navigate": "{page} पेज खोल रहा हूँ।",
        "agent": "यह काम एजेंट को भेज दिया: “{text}”। कमांड सेंटर में योजना देखकर मंज़ूरी दें।",
        "agent_other": "मैंने “{text}” एजेंट को भेज दिया है। फ़ाइल और ऐप के काम अंग्रेज़ी में बेहतर समझे जाते हैं।",
        "cant": "यह काम यहाँ नहीं हो सकता। {reason}", "done": "हो गया। {msg}",
        "confirm_power": "कृपया पुष्टि करें। {reason} जारी रखने के लिए Confirm दबाएँ।",
        "confirm_kill": "क्या आप {name} (PID {pid}) बंद करना चाहते हैं? उसमें बिना सेव किया काम खो जाएगा।",
        "refuse_kill": "मैं {name} बंद नहीं करूँगा: {reason}", "no_proc": "“{name}” नाम का कोई प्रोसेस नहीं चल रहा।",
        "top": "सबसे ज़्यादा इस्तेमाल करने वाले प्रोग्राम: {items}।", "cpu": "सीपीयू का इस्तेमाल {v} प्रतिशत है।",
        "mem": "मेमोरी का इस्तेमाल {v} प्रतिशत है, और {free} खाली है।", "disk": "डिस्क: {txt}।",
        "no_battery": "कोई बैटरी नहीं मिली, यह कंप्यूटर बिजली पर चल रहा है।", "battery": "बैटरी {v} प्रतिशत है, {state}।",
        "plugged": "चार्जर लगा है", "on_battery": "बैटरी पर चल रहा है", "uptime": "सिस्टम {up} से चल रहा है।",
        "net": "जुड़े नेटवर्क: {txt}।", "no_net": "कोई सक्रिय नेटवर्क नहीं मिला।",
        "status": "सिस्टम की सेहत 100 में से {score}। सीपीयू {cpu} प्रतिशत, मेमोरी {mem} प्रतिशत, डिस्क {disk} प्रतिशत, और सिस्टम {up} से चल रहा है।",
    },
    "ar": {
        "didnt_catch": "عذراً، لم أفهم. حاول مرة أخرى.", "hello": "مرحباً! أنا وكيل سطح المكتب. اسألني عن حالة النظام أو البطارية أو الوقت.",
        "time": "الساعة الآن {time}.", "date": "اليوم {date}.", "thanks": "على الرحب والسعة!", "stop": "تم طلب الإيقاف الطارئ.",
        "nothing_running": "لا يوجد شيء قيد التشغيل الآن.", "navigate": "جارٍ فتح صفحة {page}.",
        "agent_other": "أرسلت “{text}” إلى الوكيل. مهام الملفات والتطبيقات تُفهم بشكل أفضل بالإنجليزية.",
        "cant": "لا يمكنني فعل ذلك هنا. {reason}", "done": "تم. {msg}", "confirm_power": "يرجى التأكيد. {reason} اضغط Confirm للمتابعة.",
        "confirm_kill": "هل تريد إنهاء {name} (PID {pid})؟ سيضيع العمل غير المحفوظ.", "refuse_kill": "لن أنهي {name}: {reason}",
        "cpu": "استخدام المعالج {v} بالمئة.", "mem": "استخدام الذاكرة {v} بالمئة، والمتاح {free}.", "disk": "القرص: {txt}.",
        "no_battery": "لا توجد بطارية.", "battery": "البطارية {v} بالمئة، {state}.", "plugged": "موصولة بالشاحن", "on_battery": "تعمل على البطارية",
        "uptime": "النظام يعمل منذ {up}.", "status": "صحة النظام {score} من 100. المعالج {cpu} بالمئة، الذاكرة {mem} بالمئة، القرص {disk} بالمئة.",
        "top": "أكثر العمليات استخداماً: {items}.",
    },
    "fa": {
        "didnt_catch": "متوجه نشدم. دوباره بگویید.", "hello": "سلام! من دستیار دسکتاپ شما هستم.", "time": "ساعت {time} است.",
        "date": "امروز {date} است.", "thanks": "خواهش می‌کنم!", "stop": "توقف اضطراری درخواست شد.", "cpu": "مصرف پردازنده {v} درصد است.",
        "mem": "مصرف حافظه {v} درصد است و {free} آزاد است.", "battery": "باتری {v} درصد است، {state}.", "plugged": "به برق وصل است",
        "on_battery": "با باتری کار می‌کند", "no_battery": "باتری پیدا نشد.", "uptime": "سیستم از {up} پیش روشن است.",
        "status": "امتیاز سلامت سیستم {score} از 100. پردازنده {cpu} درصد، حافظه {mem} درصد، دیسک {disk} درصد.",
        "agent_other": "«{text}» را برای عامل فرستادم. کارهای فایل و برنامه به انگلیسی بهتر فهمیده می‌شوند.",
        "cant": "اینجا نمی‌توانم این کار را انجام دهم. {reason}", "done": "انجام شد. {msg}",
        "confirm_power": "لطفاً تأیید کنید. {reason}", "navigate": "در حال باز کردن صفحه {page}.",
    },
    "tr": {
        "didnt_catch": "Anlayamadım, lütfen tekrar söyleyin.", "hello": "Merhaba! Ben masaüstü asistanınızım.", "time": "Saat {time}.",
        "date": "Bugün {date}.", "thanks": "Rica ederim!", "stop": "Acil durdurma istendi.", "nothing_running": "Şu anda çalışan bir şey yok.",
        "navigate": "{page} sayfası açılıyor.", "agent_other": "“{text}” komutunu asistana gönderdim. Dosya ve uygulama görevleri en iyi İngilizce anlaşılır.",
        "cant": "Bunu burada yapamam. {reason}", "done": "Tamam. {msg}", "confirm_power": "Lütfen onaylayın. {reason}",
        "confirm_kill": "{name} (PID {pid}) kapatılsın mı? Kaydedilmemiş işler kaybolur.", "cpu": "İşlemci kullanımı yüzde {v}.",
        "mem": "Bellek kullanımı yüzde {v}, boş {free}.", "disk": "Disk: {txt}.", "no_battery": "Pil bulunamadı.",
        "battery": "Pil yüzde {v}, {state}.", "plugged": "şarjda", "on_battery": "pilde", "uptime": "Sistem {up} süredir açık.",
        "status": "Sistem sağlığı 100 üzerinden {score}. İşlemci yüzde {cpu}, bellek yüzde {mem}, disk yüzde {disk}.",
        "top": "En çok kullanan işlemler: {items}.",
    },
    "fr": {
        "didnt_catch": "Je n'ai pas compris. Répétez, s'il vous plaît.", "hello": "Bonjour ! Je suis votre agent de bureau.",
        "time": "Il est {time}.", "date": "Nous sommes le {date}.", "thanks": "Avec plaisir !", "stop": "Arrêt d'urgence demandé.",
        "nothing_running": "Rien n'est en cours.", "navigate": "J'ouvre la page {page}.",
        "agent_other": "J'ai envoyé « {text} » à l'agent. Les tâches fichiers et applications sont mieux comprises en anglais.",
        "cant": "Je ne peux pas faire cela ici. {reason}", "done": "C'est fait. {msg}", "confirm_power": "Veuillez confirmer. {reason}",
        "confirm_kill": "Fermer {name} (PID {pid}) ? Le travail non enregistré sera perdu.", "cpu": "Le processeur est utilisé à {v} pour cent.",
        "mem": "La mémoire est utilisée à {v} pour cent, {free} disponibles.", "disk": "Disque : {txt}.", "no_battery": "Aucune batterie détectée.",
        "battery": "La batterie est à {v} pour cent, {state}.", "plugged": "branchée", "on_battery": "sur batterie",
        "uptime": "Le système tourne depuis {up}.", "top": "Processus les plus gourmands : {items}.",
        "status": "Score de santé {score} sur 100. Processeur {cpu} pour cent, mémoire {mem} pour cent, disque {disk} pour cent.",
    },
    "es": {
        "didnt_catch": "No te entendí. Repítelo, por favor.", "hello": "¡Hola! Soy tu agente de escritorio.", "time": "Son las {time}.",
        "date": "Hoy es {date}.", "thanks": "¡De nada!", "stop": "Parada de emergencia solicitada.", "nothing_running": "No hay nada en ejecución.",
        "navigate": "Abriendo la página {page}.", "agent_other": "Envié «{text}» al agente. Las tareas de archivos y apps se entienden mejor en inglés.",
        "cant": "No puedo hacer eso aquí. {reason}", "done": "Hecho. {msg}", "confirm_power": "Por favor confirma. {reason}",
        "confirm_kill": "¿Cerrar {name} (PID {pid})? Se perderá el trabajo sin guardar.", "cpu": "El uso del procesador es del {v} por ciento.",
        "mem": "El uso de memoria es del {v} por ciento, con {free} libres.", "disk": "Disco: {txt}.", "no_battery": "No se detectó batería.",
        "battery": "La batería está al {v} por ciento, {state}.", "plugged": "conectada", "on_battery": "con batería",
        "uptime": "El sistema lleva encendido {up}.", "top": "Procesos que más consumen: {items}.",
        "status": "Salud del sistema {score} de 100. Procesador {cpu} por ciento, memoria {mem} por ciento, disco {disk} por ciento.",
    },
    "de": {
        "didnt_catch": "Das habe ich nicht verstanden. Bitte wiederholen.", "hello": "Hallo! Ich bin Ihr Desktop-Agent.",
        "time": "Es ist {time}.", "date": "Heute ist {date}.", "thanks": "Gern geschehen!", "stop": "Notstopp angefordert.",
        "nothing_running": "Gerade läuft nichts.", "navigate": "Ich öffne die Seite {page}.",
        "agent_other": "Ich habe „{text}“ an den Agenten geschickt. Datei- und App-Aufgaben versteht er am besten auf Englisch.",
        "cant": "Das geht hier nicht. {reason}", "done": "Erledigt. {msg}", "confirm_power": "Bitte bestätigen. {reason}",
        "confirm_kill": "{name} (PID {pid}) beenden? Ungespeicherte Arbeit geht verloren.", "cpu": "Die CPU-Auslastung beträgt {v} Prozent.",
        "mem": "Der Arbeitsspeicher ist zu {v} Prozent belegt, {free} frei.", "disk": "Festplatte: {txt}.", "no_battery": "Kein Akku gefunden.",
        "battery": "Der Akku ist bei {v} Prozent, {state}.", "plugged": "am Netz", "on_battery": "im Akkubetrieb",
        "uptime": "Das System läuft seit {up}.", "top": "Prozesse mit der höchsten Last: {items}.",
        "status": "Systemgesundheit {score} von 100. CPU {cpu} Prozent, Speicher {mem} Prozent, Festplatte {disk} Prozent.",
    },
    "it": {
        "didnt_catch": "Non ho capito. Ripeti, per favore.", "hello": "Ciao! Sono il tuo agente desktop.", "time": "Sono le {time}.",
        "date": "Oggi è {date}.", "thanks": "Prego!", "stop": "Arresto di emergenza richiesto.", "cpu": "L'uso del processore è del {v} percento.",
        "mem": "L'uso della memoria è del {v} percento, {free} liberi.", "battery": "La batteria è al {v} percento, {state}.",
        "plugged": "in carica", "on_battery": "a batteria", "no_battery": "Nessuna batteria rilevata.",
        "status": "Salute del sistema {score} su 100. Processore {cpu} percento, memoria {mem} percento, disco {disk} percento.",
        "cant": "Non posso farlo qui. {reason}", "done": "Fatto. {msg}", "confirm_power": "Conferma, per favore. {reason}",
        "agent_other": "Ho inviato «{text}» all'agente. I compiti su file e app si capiscono meglio in inglese.",
    },
    "pt": {
        "didnt_catch": "Não entendi. Repita, por favor.", "hello": "Olá! Sou o seu agente de desktop.", "time": "São {time}.",
        "date": "Hoje é {date}.", "thanks": "De nada!", "stop": "Parada de emergência solicitada.", "cpu": "O uso do processador é de {v} por cento.",
        "mem": "O uso de memória é de {v} por cento, {free} livres.", "battery": "A bateria está em {v} por cento, {state}.",
        "plugged": "carregando", "on_battery": "na bateria", "no_battery": "Nenhuma bateria detectada.", "uptime": "O sistema está ligado há {up}.",
        "status": "Saúde do sistema {score} de 100. Processador {cpu} por cento, memória {mem} por cento, disco {disk} por cento.",
        "cant": "Não posso fazer isso aqui. {reason}", "done": "Feito. {msg}", "confirm_power": "Por favor, confirme. {reason}",
        "agent_other": "Enviei “{text}” ao agente. Tarefas de arquivos e apps são melhor entendidas em inglês.",
    },
    "ru": {
        "didnt_catch": "Не расслышал. Повторите, пожалуйста.", "hello": "Здравствуйте! Я ваш помощник рабочего стола.",
        "time": "Сейчас {time}.", "date": "Сегодня {date}.", "thanks": "Пожалуйста!", "stop": "Запрошена аварийная остановка.",
        "nothing_running": "Сейчас ничего не выполняется.", "navigate": "Открываю страницу {page}.",
        "agent_other": "Я отправил «{text}» агенту. Задачи с файлами и приложениями лучше понимаются на английском.",
        "cant": "Здесь это сделать нельзя. {reason}", "done": "Готово. {msg}", "confirm_power": "Пожалуйста, подтвердите. {reason}",
        "confirm_kill": "Завершить {name} (PID {pid})? Несохранённые данные будут потеряны.", "cpu": "Загрузка процессора {v} процентов.",
        "mem": "Использование памяти {v} процентов, свободно {free}.", "disk": "Диск: {txt}.", "no_battery": "Батарея не обнаружена.",
        "battery": "Заряд батареи {v} процентов, {state}.", "plugged": "подключено к сети", "on_battery": "от батареи",
        "uptime": "Система работает {up}.", "top": "Самые ресурсоёмкие процессы: {items}.",
        "status": "Оценка здоровья системы {score} из 100. Процессор {cpu} процентов, память {mem} процентов, диск {disk} процентов.",
    },
    "zh": {
        "didnt_catch": "抱歉，我没听清，请再说一遍。", "hello": "你好！我是你的桌面助手。", "time": "现在是{time}。", "date": "今天是{date}。",
        "thanks": "不客气！", "stop": "已请求紧急停止。", "nothing_running": "现在没有正在运行的任务。", "navigate": "正在打开{page}页面。",
        "agent_other": "我已把“{text}”发送给代理。文件和应用任务用英语表达效果最好。", "cant": "这里无法执行。{reason}", "done": "完成。{msg}",
        "confirm_power": "请确认。{reason}", "confirm_kill": "要结束 {name}（PID {pid}）吗？未保存的工作将丢失。",
        "cpu": "处理器使用率为百分之{v}。", "mem": "内存使用率为百分之{v}，可用 {free}。", "disk": "磁盘：{txt}。", "no_battery": "未检测到电池。",
        "battery": "电池电量百分之{v}，{state}。", "plugged": "正在充电", "on_battery": "使用电池", "uptime": "系统已运行 {up}。",
        "status": "系统健康分数 {score}（满分100）。处理器百分之{cpu}，内存百分之{mem}，磁盘百分之{disk}。", "top": "占用最多的进程：{items}。",
    },
}


def lang_info(code: str) -> dict:
    return LANGS.get(code, LANGS["en"])


def full_support(code: str) -> bool:
    return code.startswith("en") or code in KW


def t(key: str, lang: str = "en", **kw) -> str:
    tpl = T.get(lang, {}).get(key) or T.get(lang.split("-")[0], {}).get(key) or T["en"][key]
    try:
        return tpl.format(**kw)
    except (KeyError, IndexError):
        return T["en"][key].format(**kw)


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ي", "ی").replace("ك", "ک").split())


def to_command(text: str, lang: str) -> str | None:
    """Map a native-language phrase to a canonical English command, or None."""
    tables = [KW.get(lang, {})] + ([KW["hi"]] if lang == "ur" else []) + ([KW["ur"]] if lang == "hi" else [])
    s = _norm(text)
    for canon in CANON:
        for table in tables:
            if any(_norm(k) in s for k in table.get(canon, [])):
                return canon
    return None


# ---------------------------------------------------------------- Devanagari → Urdu script (approximate)
_CONS = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
                 ["ک", "کھ", "گ", "گھ", "ن", "چ", "چھ", "ج", "جھ", "ن", "ٹ", "ٹھ", "ڈ", "ڈھ", "ن", "ت", "تھ", "د", "دھ",
                  "ن", "پ", "پھ", "ب", "بھ", "م", "ی", "ر", "ل", "و", "ش", "ش", "س", "ہ"]))
_NUKTA = {"क": "ق", "ख": "خ", "ग": "غ", "ज": "ز", "फ": "ف", "ड": "ڑ", "ढ": "ڑھ"}
_INDEP = {"अ": "ا", "आ": "آ", "इ": "ا", "ई": "ای", "उ": "ا", "ऊ": "او", "ए": "ا", "ऐ": "اے", "ओ": "او", "औ": "او", "ऋ": "ر"}
_MATRA = {"ा": "ا", "ि": "", "ी": "ی", "ु": "", "ू": "و", "ो": "و", "ौ": "و", "ृ": "ر", "्": "", "ः": "ہ"}
_PRE = {"क़": "ق", "ख़": "خ", "ग़": "غ", "ज़": "ز", "फ़": "ف", "ड़": "ڑ", "ढ़": "ڑھ"}


def deva_to_urdu(text: str) -> str:
    for k, v in _PRE.items():
        text = text.replace(k, v)
    out, n = [], len(text)
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < n else " "
        end = not ("ऀ" <= nxt <= "ॿ")
        if ch in _CONS:
            out.append(_NUKTA[ch] if nxt == "़" and ch in _NUKTA else _CONS[ch])
        elif ch == "़":
            continue
        elif ch in _INDEP:
            out.append(_INDEP[ch])
        elif ch in "ेै":
            out.append("ے" if end else "ی")
        elif ch in "ंँ":
            out.append("ں" if end else "ن")
        elif ch in _MATRA:
            out.append(_MATRA[ch])
        elif "०" <= ch <= "९":
            out.append(chr(ord("۰") + ord(ch) - ord("०")))
        elif ch == "।":
            out.append("۔")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()
