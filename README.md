# Quran Automation

## العربية
أداة تنشئ فيديوهات قرآنية قصيرة وطويلة وتنشرها تلقائيًا على YouTube. تجمع الآيات والتلاوة والخلفية والترجمة، ثم تتحقق من الفيديو بعد الرفع.

يعمل النشر تلقائيًا من خلال GitHub Actions. ضع OAuth الخاص بقناتك في Secret باسم `TOKEN_BASE64`، ولا تضع أي Token داخل الكود أو Issues. كل مستخدم يشغّل الأداة على القناة المرتبطة بتوكنه هو.

## English
An automation tool that creates short and long Quran videos and publishes them to YouTube. It combines verses, recitation, backgrounds, and translations, then verifies each upload.

Publishing runs through GitHub Actions. Store your own channel OAuth data in the `TOKEN_BASE64` Secret and never place tokens in source code or issues. Each user runs the project on the channel linked to their own token.

## Testing
```bash
python -m unittest test_monitoring.py test_render_profile.py
```

## License
Quran Automation Community License — see [LICENSE](LICENSE).

You may use and modify the project for non-commercial purposes and monetize videos created with it on YouTube. Selling or commercially licensing the code or derivative software is not permitted.

Copyright (c) 2026 Mohamed Abdalnaby.
