### Nativo

Mesmos degraus e mesmas cores; só a unidade muda (pt no iOS, sp e dp no Android).

| Conceito | iOS (SwiftUI) | Android (Compose) |
| --- | --- | --- |
| Rampa | `@ScaledMetric(relativeTo: .body) var n = 17` e `.font(.system(size: n, weight: .regular))`, com os degraus da rampa. `.font(.system(size:))` sozinho ignora o Dynamic Type | `TextStyle(fontSize = 17.sp)`, com os degraus da rampa |
| Tabular | `.monospacedDigit()` | `TextStyle(fontFeatureSettings = "tnum")` |
| Raio | `RoundedRectangle(cornerRadius: 12)` | `RoundedCornerShape(12.dp)` |
| Alvo no toque | 44pt | 48dp, o mínimo do Material, acima dos 44 do documento |
| Lista agrupada | `List { }.listStyle(.insetGrouped)` | `Card` + `Divider` recuado |
| Acento | `.tint(accent)` | `colorScheme.primary` |

---
