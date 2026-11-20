# ربط نموذج تاسك ١٣ بتطبيق Android

ملفات `assets` هي النموذج ONNX، ملف معاملات الإدخال والعتبة JSON، و٢٠ عينة تطابق للاختبار على الجهاز. كلاس Kotlin جاهز للنسخ داخل مشروع التطبيق، لكن لا يوجد مشروع Android في ملفات المشروع المرسلة؛ لذلك **لم يتم تركيبه أو تشغيل الاختبار على هاتف/محاكي**.

1. انسخ `AihmAnomalyDetector.kt` إلى كود التطبيق، وعدل اسم `package` لاسم مشروعكم.
2. انسخ الملفات الثلاثة داخل `android/assets/` إلى `app/src/main/assets/`، وانسخ `Task13ParityInstrumentedTest.kt` إلى `app/src/androidTest/...`. ملف عينات الاختبار يمكن وضعه في `src/main/assets` كما في المثال.
3. في ملف Gradle الخاص بالتطبيق أضف مكتبة `com.microsoft.onnxruntime:onnxruntime-android` و repository `mavenCentral()`، وثبت نسخة مدعومة في مشروعكم. أضف AndroidX test إذا لم تكن موجودة.
4. بعد إغلاق كل نافذة ٥ دقائق، احسب متوسط النبض BPM، ومرّر عدد الخطوات إن كان موجودًا، أو `null` عند غيابه. استخدم `scoreWindow(meanHrBpm, stepsTotal)` ثم `flagged` في منطق التنبيهات، مع قواعد الاستمرار والنشاط المعتمدة بالتطبيق. **لا ترسل قراءة كل ثانية بوصفها نافذة كاملة.**
5. شغّل اختبار Android المرفق؛ يقارن الدرجة والقرار على ٢٠ عينة مع نتائج بايثون، ويسجل نجاح تطابق الهاتف. لا تعتبر تطابق Python/ONNX وحده اختبار هاتف.

المدخلات حسب الترتيب: `hr_bpm`, `steps_total`, `steps_missing`. لا يوجد standard scaler رقمي؛ تعويض الخطوات الناقصة مضمن داخل ONNX. حد القرار موجود داخل `scaler_and_inference.json` (`score_samples <= threshold`). المصدر النموذجي Figshare، وتجربة ليان ونوف انتقال مجال غير موسومة.
