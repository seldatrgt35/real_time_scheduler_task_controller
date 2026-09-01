# S32K148 elle instruction-cycle deneyi

Bu deney, kaynak kodu tahmininden önce ölçüm zincirini anlaşılır ve
tekrarlanabilir hale getirir:

1. Deterministik otomotiv C taskı GCC 11.4 ile derlenir.
2. Derleyicinin gerçekten ürettiği Thumb-2 assembly `objdump` ile alınır.
3. Başlangıç verilerinin çalıştırdığı yol instruction instruction sayılır.
4. Cortex-M4 çekirdek maliyeti ile S32K148 PFlash etkisi birbirinden ayrılır.
5. Aynı ELF kartta DWT çevrim sayacıyla 40 kez ölçülür.
6. Aynı C taskı Gemini'ye verilip üç sonuç karşılaştırılır.

## C kodunun yaptığı iş

`ThrottleActuatorMonitor_Task5ms` dört aktüatör kanalı işler. Her iterasyonda:

- `ClampCommandU16`: komutu 500..3500 aralığına sınırlar.
- `RateLimitU16`: bir çağrıda değişimi en fazla 120 yapar.
- `UpdateDebounceU8`: feedback fault sayacını artırır veya azaltır.
- Sonucu volatile çıkış dizisine yazar ve checksum günceller.

Başlangıç verisi sabittir. Böylece seçilen yol tekrar üretilebilir:

- Döngü gövdesi: 4 kez, döngü testi: 5 kez.
- Clamp: 3 normal yol, 1 üst sınır yolu.
- Rate limit: 4 kez pozitif değişim, farkların tamamı 120 veya altı.
- Debounce: 2 aktif, 2 pasif feedback yolu.
- Her helper 4 kez, toplam 12 doğrudan çağrı.

## Derleme

```powershell
powershell -ExecutionPolicy Bypass -File experiments/manual_instruction_baseline/build_s32k148.ps1
```

Ana seçenek `-O0`'dır. Ayrıca builtin dönüşümü, inline, sibling-call dönüşümü,
frame-pointer kaldırma, IPA ve LTO açıkça kapatılmıştır. Bu seçenekler kodu
"C satırı başına bir instruction" yapmaz; GCC yine ABI gereği prologue,
epilogue, stack erişimi ve register aktarımı üretir. Doğru kaynak bu nedenle
oluşturulan disassembly'dir:

`artifacts/s32k148_manual_instruction_baseline/star_s32k148_manual_instruction_baseline.disasm.txt`

## Elle yol sayımı

```powershell
python experiments/manual_instruction_baseline/manual_cycle_analysis.py
```

Script yalnız seçilen gerçek yol üzerindeki assembly adreslerini toplar. Literal
pool, alignment ve çalışmayan branch gövdeleri dinamik hesaba girmez. Çıktı:

`artifacts/s32k148_manual_instruction_baseline/manual_path_cycle_ledger.json`

Ledger şu sınıfları ayrı gösterir: ALU/move/compare/shift, load, store,
push/pop register transferleri, BL, dönüş, taken/not-taken conditional branch
ve unconditional branch.

Önemli: ARM Cortex-M4 TRM instruction timing bilgisini verir; MCU üreticisinin
bellek sistemi ayrıca ele alınmalıdır. S32K148 Reference Manual da clock/Flash
yapılandırmasını tanımlar. PFlash wait-state/prefetch durumu kesinleşmeden bu
etki yüzde veya katsayı olarak çekirdek toplamına eklenmez. Bu yüzden ledger
sonucu önce `manual_core_cycles`, kart sonucu ise `measured_total_cycles` olarak
ayrı tutulur.

Resmi başvuru kaynakları:

- ARM Cortex-M4 TRM r0p1: https://developer.arm.com/documentation/100166/0001
- ARM Cortex-M kaynak kataloğu: https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/cortex-m-resources
- NXP S32K1 ürün ve Reference Manual sayfası: https://www.nxp.com/products/S32K1

## Kartta izlenecek ifadeler

```text
g_star_manual_complete
g_star_manual_results.completed_samples
g_star_manual_results.measurement_overhead_cycles
g_star_manual_results.error_flags
g_star_manual_results.mean_execution_cycles
g_star_manual_results.max_execution_cycles
g_star_manual_results.mean_execution_us_x1000
g_star_manual_results.max_execution_us_x1000
```

Geçerli koşul: `complete=1`, `completed_samples=40`, `error_flags=0`.

## Gemini tahmini

```powershell
python -m gemini_rag_cycle_prototype.cli --source "experiments/manual_instruction_baseline/manual_automotive_task.c" --function ThrottleActuatorMonitor_Task5ms --no-rag --output "gemini_rag_cycle_prototype/results/manual_instruction_baseline_gemini.json"
```

Karşılaştırılacak üç sayı:

- Elle hesap: `manual_core_cycles`
- Gemini: JSON içindeki tahmin cycle değeri
- Kart: `max_execution_cycles`

Kart ölçümü, instruction çekirdeğine ek olarak gerçek PFlash/bus/pipeline
davranışını içerir. Bu nedenle ilk karşılaştırma yalnız farkı gösterecek; farkı
keyfi katsayıya dönüştürmeyecektir.
