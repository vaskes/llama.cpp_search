# RESTART_GOTCHA — почему твой `llama-ornith.service` лупил 3000+ раз

**Симптом:** после `systemctl disable llama-ornith.service` он всё равно запускается и рестартанул тысячи раз в loop.

**Причина:** в `llama-ornith.service` стояло:
```ini
Restart=on-failure
RestartSec=10
```

`systemctl disable` снимает **только автостарт при загрузке**. Если сервис **уже запущен**, он продолжает работать. А если он упал — `Restart=on-failure` его перезапустит через 10 сек. Если он падает опять — **бесконечный loop**, restart counter растёт.

**Как увидеть loop:**
```bash
journalctl -u llama-ornith.service | grep "Scheduled restart"
# Sep 03 11:20:04 llama-ornith.service: Scheduled restart job, restart counter is at 3323.
```

**Фикс — для сервисов, которые ты стартуешь руками:**
```ini
[Service]
Restart=no    # или вообще удалить строку
```

`Restart=no` означает: упал — лежи мёртвым, жди ручного `systemctl start`.

**Альтернатива — `Restart=Prevent`:**
- Сервис не рестартует, пока ты сам не сделаешь `systemctl reset-failed` + `start`.

**Когда Restart=on-failure OK:**
- Network services без жёстких зависимостей на порт (HTTP-сервер, который должен быть всегда up)
- Не наш случай: у нас несколько llama-сервисов на 8080, нельзя чтобы они все пытались.

**Рекомендация для всех `llama-*.service` на этой машине:**
Замени `Restart=on-failure` → `Restart=no` (или удали строку), чтобы случайно два сервиса не дрались за 8080.
