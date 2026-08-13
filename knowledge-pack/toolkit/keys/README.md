# keys/ — ملفات مفاتيح API

ملف لكل خدمة. اصطلاح التسمية: `<service>.key` (أو `<service>.yml` لإعدادات YAML).

## إضافة مفتاح (بدون إخبار الوكيل)

```bash
printf '%s\n' 'YOUR-KEY' > ~/.hermes/toolkit/keys/<service>.key
chmod 600 ~/.hermes/toolkit/keys/<service>.key
bash ~/.hermes/toolkit/toolkit-scan.sh
```

الوكيل سيراه في `inventory.yaml` (مقنّعاً) ويقرأ الملف عند الحاجة.

## قواعد
- لا تضع هذه الملفات في git أبداً.
- لا تترك مفتاحاً مقروءاً للجميع — الماسح يتجاهل الملفات المفتوحة.
- إذا كان المفتاح يخص أداة بموقعها الخاص (subfinder، vulners، ngrok...)، أبقِه هناك — الماسح يقرأ تلك المواقع تلقائياً؛ هذا المجلد للأشياء الأخرى.
