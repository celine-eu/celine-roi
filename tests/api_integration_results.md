# CELINE ROI — API Integration Test Results

**Date:** 2026-03-30
**API:** http://localhost:8018/api/v1

## Scenario Tests

| # | Test | kWp | Prod | Cons | CAPEX | Regime | HTTP | NPV | IRR | Payback | Auto% | CER lib y1 | Balance | F/W |
|---|------|----:|-----:|-----:|------:|--------|-----:|----:|----:|--------:|------:|-----------:|---------|-----|
| | T01 Tiny residential 3kWp RID_CER | 3 | 3600 | 2000 | 5400 | RID_CER | 200 | 38 | 5.6% | 14.7 | 19.2% | 85 | OK | 0F/1W |
| | T02 Typical residential 6kWp RID_CER | 6 | 7200 | 3500 | 8400 | RID_CER | 200 | 2,294 | 8.1% | 10.1 | 16.9% | 175 | OK | 0F/0W |
| | T03 Oversized 10kWp/2500kWh RID_CER | 10 | 12000 | 2500 | 11500 | RID_CER | 200 | 2,544 | 7.6% | 10.5 | 7.3% | 326 | OK | 0F/0W |
| | T04 Huge consumption 3kWp/15000kWh | 3 | 3600 | 15000 | 5400 | RID_CER | 200 | 8,270 | 17.3% | 5.8 | 89.7% | 10 | OK | 0F/2W |
| | T05 Zero consumption (pure export) | 6 | 7200 | 0 | 8000 | RID | 200 | -2,733 | 1.6% | 21.2 | 0.0% | 0 | OK | 0F/0W |
| | T06 Production = Consumption | 4 | 4000 | 4000 | 6000 | RID_CER | 200 | 1,798 | 8.3% | 9.9 | 32.5% | 79 | OK | 0F/0W |
| | T07 Large commercial 100kWp | 100 | 120000 | 80000 | 90000 | RID_CER | 200 | 111,683 | 15.4% | 6.5 | 22.6% | 2716 | OK | 0F/0W |
| | T08 Industrial 500kWp | 500 | 600000 | 400000 | 400000 | RID_CER | 200 | 607,886 | 17.3% | 5.9 | 22.6% | 13580 | OK | 0F/0W |
| | T09 Financed 70% 45kWp | 45 | 49500 | 40000 | 45000 | RID_CER | 200 | 49,141 | 26.1% | 4.2 | 26.8% | 1058 | OK | 0F/0W |
| | T10 RID only 10kWp | 10 | 12000 | 8000 | 11000 | RID | 200 | 7,614 | 11.3% | 8.4 | 22.6% | 0 | OK | 0F/0W |
| | T11 CER only 10kWp | 10 | 12000 | 8000 | 11000 | CER | 200 | 1,373 | 6.7% | 12.6 | 22.6% | 272 | OK | 0F/0W |
| | T12 Heat pump profile 6kWp | 6 | 7200 | 4500 | 8400 | RID_CER | 200 | 3,353 | 9.1% | 9.5 | 21.3% | 166 | OK | 0F/0W |
| | T13 1kWp minimum system | 1 | 1200 | 1000 | 2000 | RID | 200 | -388 | 3.5% | 19.4 | 27.6% | 0 | OK | 0F/1W |
| | T14 100% financed equity=0 | 20 | 24000 | 15000 | 22000 | RID_CER | 200 | 20,144 | — | 0.0 | 21.3% | 552 | OK | 0F/0W |
| | T15 High WACC 10% | 20 | 24000 | 15000 | 20000 | RID_CER | 200 | 19,260 | 13.5% | 7.3 | 21.3% | 552 | OK | 0F/0W |
| | T12b Heat pump profile 6kWp | 6 | 7200 | 4500 | 8400 | RID_CER | 200 | 9,822 | 14.8% | 6.7 | 47.8% | 109 | — | 0F/0W |
| | T15b High WACC 10% | 20 | 24000 | 15000 | 20000 | RID_CER | 200 | 5,933 | 13.5% | 7.3 | 21.3% | 552 | — | 0F/0W |
| | T16 Low retail price 0.15 | 20 | 24000 | 15000 | 20000 | RID_CER | 200 | 10,097 | 10.0% | 9.0 | 21.3% | 552 | — | 0F/0W |
| | T17 Negative CAPEX | | | | | | **400** | | | | | | | `system → capex: Input should be greater than 0` |
| | T18 Missing required fields | | | | | | **400** | | | | | | | `system → latitude: Field required; system → longitude: Field` |
| | T19 Invalid regime SSP | | | | | | **400** | | | | | | | `system → regime: Input should be 'RID', 'CER' or 'RID_CER'` |

## Error Handling Tests

| Test | HTTP | Error Message |
|------|-----:|---------------|
| T17 Negative CAPEX | 400 | system → capex: Input should be greater than 0 |
| T18 Missing required fields | 400 | system → latitude: Field required; system → longitude: Field required; system → capex: Field required; system → annual_consumption_kwh: Field required |
| T19 Invalid regime SSP | 400 | system → regime: Input should be 'RID', 'CER' or 'RID_CER' |

## CAPEX Estimator Tests (200 m² rooftop)

| Panels | kWp | CAPEX (EUR) | EUR/kWp | Rooftop % |
|-------:|----:|------------:|--------:|----------:|
| 4 | 1.8 | 2,516 | 1,398 | 3.9% |
| 10 | 4.5 | 5,635 | 1,252 | 9.8% |
| 25 | 11.2 | 12,621 | 1,122 | 24.5% |
| 50 | 22.5 | 23,228 | 1,032 | 49.0% |
| 75 | 33.8 | 33,187 | 983 | 73.5% |
| 100 | 45.0 | 42,748 | 950 | 98.0% |

## Scenario Comparator Test

**HTTP:** 200 | **Scenarios:** Base (RID+CER) / Solo RID / Finanziato 70% / Pompa di calore

| KPI | Base (RID+CER)  | Solo RID  | Δ  | Finanziato 70%  | Δ  | Pompa di calore  | Δ  |
|--- |---: |---: |---: |---: |---: |---: |---: |
| VAN  | 16,096  | 12,744  | -3,353  | 17,895  | +1,799  | 33,696  | +17,599  |
| TIR  | 12.3%  | 10.9%  | -1.4pp  | 22.8%  | +10.4pp  | 18.2%  | +5.9pp  |
| Payback semplice  | 7.8  | 8.6  | +0.9  | 4.7  | -3.0  | 5.7  | -2.1  |
| Payback attualizzato  | 10.2  | 12.5  | +2.4  | 5.6  | -4.6  | 6.9  | -3.3  |
| Autoconsumo  | 17.4%  | 17.4%  | —  | 17.4%  | —  | 38.9%  | +21.5pp  |
| Produzione anno 1  | 23,640  | 23,640  | —  | 23,640  | —  | 23,640  | —  |
| CER libero anno 1  | 580  | 0  | -580  | 580  | —  | 426  | -154  |
| Utile cumulato  | 49,503  | 43,914  | -5,590  | 45,270  | -4,233  | 85,365  | +35,862  |
| DSCR min  | —  | —  | —  | 1.82  | —  | —  | —  |
| Valido?  | ✓  | ✓  | —  | ✓  | —  | ✓  | —  |