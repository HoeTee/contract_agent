# 鐢ㄦ埛绠＄悊

鏈枃鏄」鐩敤鎴风鐞嗕笓棰樻枃妗ｏ紝瑕嗙洊鏅€氱敤鎴风晫闈€佺鐞嗗憳鐣岄潰銆佸悗绔暟鎹€佸鏌ヨ鐐广€丆LI 鍜?Docker 閮ㄧ讲钀界偣銆傚墠绔畬鏁寸敤鎴锋梾绋嬨€侀〉闈㈢姸鎬佸拰澶氭爣绛鹃〉琛屼负瑙?`docs/FRONTEND_USER_JOURNEY.md`銆?

## 瑙掕壊鍜屽叆鍙?

褰撳墠绯荤粺鏀寔涓ょ被瑙掕壊锛?

```text
user  鏅€氱敤鎴?
admin 绠＄悊鍛?
```

瑙掕壊瀹氫箟鍦?`endpoints/runtime/auth.py` 鐨?`VALID_ROLES` 涓紝瀹為檯鍊间繚瀛樺湪鐢ㄦ埛璐﹀彿 JSON 閲屻€?

鍓嶇鍏ュ彛锛?

```text
/login        鐧诲綍椤?
/work         鏅€氱敤鎴蜂笂浼犲鏍搁〉
/history      鏅€氱敤鎴峰鏍稿巻鍙查〉
/settings     鏅€氱敤鎴疯缃〉
/admin        绠＄悊鍛樺悗鍙伴椤?
/admin/users  绠＄悊鍛樼敤鎴风鐞嗛〉
```

鐧诲綍鎴愬姛鍚庯細

- 鏅€氱敤鎴疯繘鍏?`/work`銆?
- 绠＄悊鍛樿繘鍏?`/admin`銆?
- 绠＄悊鍛樿闂?`/work`銆乣/history`銆乣/settings` 浼氳閲嶅畾鍚戝洖 `/admin`銆?

## 鏅€氱敤鎴峰墠绔?

鏅€氱敤鎴风晫闈㈢敱 `endpoints/web/user_routes.py` 鎻愪緵璺敱锛岀敱 `frontend/templates/` 涓嬬殑妯℃澘娓叉煋銆?

### `/work`

妯℃澘锛?

```text
frontend/templates/index.html
```

鑳藉姏锛?

- 涓婁紶鍚堝悓 DOCX銆?
- 鍙€変笂浼犳湰娆″鏌ヨ鐐?DOCX銆?
- 濡傛灉鏈涓嶄笂浼犲鏌ヨ鐐癸紝鍒欎娇鐢?`data/<username>/contract_criteria/criteria.docx`銆?
- 瀹℃牳涓細绂佺敤鎻愪氦鎸夐挳骞跺畾鏃跺埛鏂颁换鍔＄姸鎬併€?
- 瀹℃牳瀹屾垚鍚庢彁渚涙壒娉ㄧ増 DOCX 涓嬭浇鍏ュ彛銆?

### `/history`

妯℃澘锛?

```text
frontend/templates/history.html
```

灞曠ず瀛楁锛?

- 杈撳叆鏂囦欢鍚?
- 杈撳叆鏂囦欢澶у皬
- 涓婁紶鏃堕棿
- 瀹℃煡瑕佺偣鏉ユ簮
- 杈撳嚭鏂囦欢鍚?
- 杈撳嚭鏂囦欢澶у皬
- 杈撳嚭鏃堕棿
- 涓嬭浇鍏ュ彛

鍘嗗彶璁板綍涓嶆槸鎵弿鐩綍鐢熸垚锛岃€屾槸璇诲彇锛?

```text
data/<username>/records/review_history.json
```

璇诲啓閫昏緫鍦細

```text
loggers/review_history.py
```

### `/settings`

妯℃澘锛?

```text
frontend/templates/settings.html
```

褰撳墠鑳藉姏锛?

- 鏌ョ湅鐢ㄦ埛鍚嶃€?
- 淇敼鏄剧ず鍚嶇О `display_name`銆?

鏄剧ず鍚嶇О鍐欏洖璐﹀彿 JSON锛屼笉鏀瑰彉鐢ㄦ埛鐩綍鍚嶃€傜敤鎴风洰褰曞垎鍖哄缁堜娇鐢?`username`銆?

## 绠＄悊鍛樺墠绔?

绠＄悊鍛樺悗鍙拌矾鐢卞湪锛?

```text
endpoints/web/admin_routes.py
```

鍚庡彴鏁版嵁鑱氬悎鍦細

```text
endpoints/web/admin_services.py
```

妯℃澘锛?

```text
frontend/templates/admin_dashboard.html
frontend/templates/admin_users.html
frontend/templates/admin_user_detail.html
```

### `/admin`

灞曠ず杩愯鎽樿锛?

- 鐢ㄦ埛鎬绘暟
- 绠＄悊鍛樻暟閲?
- 绂佺敤鐢ㄦ埛鏁伴噺
- 鎴愬姛瀹℃煡鏁伴噺
- 鏈€杩戞湁瀹℃煡璁板綍鐨勭敤鎴?

杩欎簺鏁版嵁鏉ヨ嚜璐﹀彿 JSON 鍜屽悇鐢ㄦ埛鐨?`records/review_history.json`銆?

### `/admin/users`

绠＄悊鍛樺彲浠ワ細

- 鍒涘缓鐢ㄦ埛
- 璁剧疆鍒濆瀵嗙爜
- 璁剧疆鏄剧ず鍚嶇О
- 璁剧疆瑙掕壊 `user` 鎴?`admin`
- 鏌ョ湅鍏ㄩ儴鐢ㄦ埛
- 杩涘叆鐢ㄦ埛璇︽儏椤?

鍒涘缓鐢ㄦ埛鏃朵細鍚屾椂鍒濆鍖栫敤鎴锋暟鎹洰褰曪紝骞跺鍒剁郴缁熼粯璁ゅ鏌ヨ鐐广€?

### `/admin/users/{username}`

绠＄悊鍛樺彲浠ワ細

- 淇敼鐢ㄦ埛瑙掕壊
- 閲嶇疆鐢ㄦ埛瀵嗙爜
- 鍚敤鐢ㄦ埛
- 绂佺敤鐢ㄦ埛
- 鍒犻櫎鐢ㄦ埛
- 鍒犻櫎鐢ㄦ埛鏃堕€夋嫨鏄惁淇濈暀鐢ㄦ埛鏁版嵁鐩綍
- 涓嬭浇鐢ㄦ埛榛樿瀹℃煡瑕佺偣
- 涓婁紶瑕嗙洊鐢ㄦ埛榛樿瀹℃煡瑕佺偣
- 鎭㈠绯荤粺榛樿瀹℃煡瑕佺偣
- 鏌ョ湅璇ョ敤鎴峰鏍稿巻鍙?
- 鏌ョ湅璇ョ敤鎴锋棩蹇楃洰褰曞拰 API 浜嬩欢

鍒犻櫎鐢ㄦ埛鏈夊墠绔簩娆＄‘璁わ紝閫昏緫鍦細

```text
frontend/static/app.js
```

鍚庣淇濇姢锛?

- 绠＄悊鍛樹笉鑳界鐢ㄥ綋鍓嶇櫥褰曠殑鑷繁銆?
- 绠＄悊鍛樹笉鑳藉垹闄ゅ綋鍓嶇櫥褰曠殑鑷繁銆?
- 绠＄悊鍛樹笉鑳界Щ闄よ嚜宸辩殑绠＄悊鍛樿鑹层€?

## 鍚庣璐﹀彿鏁版嵁

璐﹀彿鏁版嵁璺緞鐢?`config.py` 涓殑 `USERS_FILE` 鍐冲畾銆?

榛樿鍊硷細

```text
<PROJECT_ROOT>/profiles/users.json
```

鍙互閫氳繃鐜鍙橀噺瑕嗙洊锛?

```env
profiles/users.json
```

璐﹀彿 JSON 缁撴瀯锛?

```json
{
  "users": [
    {
      "username": "user001",
      "password_hash": "pbkdf2_sha256$...",
      "display_name": "寮犱笁",
      "role": "user",
      "enabled": true,
      "created_at": "2026-06-01 12:00:00"
    }
  ]
}
```

瀛楁璇存槑锛?

```text
username             鐧诲綍鐢ㄦ埛鍚嶏紝涔熸槸鐢ㄦ埛鏁版嵁鐩綍鍚?
password_hash        PBKDF2 瀵嗙爜鍝堝笇锛屼笉淇濆瓨鏄庢枃瀵嗙爜
display_name         鍓嶇灞曠ず鍚嶇О
role                 user 鎴?admin
enabled              鏄惁鍏佽鐧诲綍
created_at           鍒涘缓鏃堕棿
role_updated_at      瑙掕壊鏇存柊鏃堕棿
password_updated_at  瀵嗙爜鏇存柊鏃堕棿
enabled_at           鍚敤鏃堕棿
disabled_at          绂佺敤鏃堕棿
```

绂佺敤鐢ㄦ埛鍚庯紝鐧诲綍椤典細鏄剧ず锛?

```text
璐﹀彿宸茶绂佺敤锛岃鑱旂郴绠＄悊鍛樸€?
```

鍙湁鐢ㄦ埛鍚嶅瓨鍦ㄣ€佸瘑鐮佹纭€佷絾 `enabled=false` 鏃舵墠鏄剧ず绂佺敤鎻愮ず銆傜敤鎴峰悕涓嶅瓨鍦ㄦ垨瀵嗙爜閿欒鏃舵樉绀虹敤鎴峰悕鎴栧瘑鐮侀敊璇€?

## 鐢ㄦ埛鏁版嵁鐩綍

鐢ㄦ埛鏁版嵁鏍圭洰褰曠敱 `config.py` 涓殑 `DATA_DIR` 鍐冲畾銆?

榛樿鍊硷細

```text
<PROJECT_ROOT>/data
```

鍙互閫氳繃鐜鍙橀噺瑕嗙洊锛?

```env
data/
```

鍒涘缓鐢ㄦ埛鍚庝細鐢熸垚锛?

```text
data/<username>/
  criteria/
    criteria.docx
  institutional_docs/
  contracts/
  reports_docx/
  records/
    review_history.json
  logs/
```

鐩綍鍒濆鍖栭€昏緫鍦細

```text
loggers/resolve_review_task_paths.py
```

## 瀹℃煡瑕佺偣

绯荤粺榛樿瀹℃煡瑕佺偣妯℃澘锛?

```text
resources/criteria/criteria.docx
```

鏂板缓鐢ㄦ埛鏃讹紝绋嬪簭浼氬鍒跺畠鍒帮細

```text
data/<username>/contract_criteria/criteria.docx
```

鏅€氱敤鎴峰湪 `/work` 涓婁紶鐨勫鏌ヨ鐐瑰彧鐢ㄤ簬鏈浠诲姟銆傜鐞嗗憳鍦ㄧ敤鎴疯鎯呴〉涓婁紶鐨勫鏌ヨ鐐逛細瑕嗙洊璇ョ敤鎴烽粯璁ゆ枃浠讹細

```text
data/<username>/contract_criteria/criteria.docx
```

瀹℃煡瑕佺偣涓婁紶鍓嶄細鍋?DOCX 鏍煎紡妫€鏌ュ拰鍐呭妫€鏌ャ€傚唴瀹规鏌ラ€昏緫鍦?`endpoints/runtime/document_validation.py`锛岀洰鏍囨槸鎷掔粷鏄庢樉涓嶆槸瀹℃煡瑕佺偣鐨?DOCX銆?

## 鍏变韩鐢ㄦ埛绠＄悊鏈嶅姟

CLI 鍜岀鐞嗗憳 Web 椤甸潰鍏辩敤鍚屼竴濂楃敤鎴风鐞嗛€昏緫锛?

```text
endpoints/web/user_management.py
```

涓昏鍑芥暟锛?

```text
create_user_account()   鍒涘缓鐢ㄦ埛骞跺垵濮嬪寲鐢ㄦ埛鐩綍
set_user_role()         淇敼鐢ㄦ埛瑙掕壊
reset_user_password()   閲嶇疆瀵嗙爜
set_user_enabled()      鍚敤鎴栫鐢ㄧ敤鎴?
delete_user_account()   鍒犻櫎鐢ㄦ埛璐﹀彿锛屽彲閫夊垹闄ょ敤鎴风洰褰?
```

杩欎簺鍑芥暟浼氬啓鍏ユ垨鏇存柊 `USERS_FILE`锛屽苟鎸夐渶瑕佸垱寤烘垨鍒犻櫎 `DATA_DIR/<username>`銆?

## CLI

CLI 鏂囦欢锛?

```text
scripts/manage_users.py
```

鏌ョ湅甯姪锛?

```powershell
python scripts/manage_users.py --help
```

鍒涘缓鏅€氱敤鎴凤細

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name 寮犱笁
```

鍒涘缓绠＄悊鍛橈細

```powershell
python scripts/manage_users.py create --username admin --password Admin123456 --display-name 绠＄悊鍛?--role admin
```

淇敼瑙掕壊锛?

```powershell
python scripts/manage_users.py set-role --username user001 --role admin
python scripts/manage_users.py set-role --username user001 --role user
```

閲嶇疆瀵嗙爜锛?

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

绂佺敤鎴栧惎鐢ㄧ敤鎴凤細

```powershell
python scripts/manage_users.py disable --username user001
python scripts/manage_users.py enable --username user001
```

鍒犻櫎璐﹀彿浣嗕繚鐣欑敤鎴锋暟鎹洰褰曪細

```powershell
python scripts/manage_users.py delete --username user001 --keep-data
```

鍒犻櫎璐﹀彿骞跺垹闄ょ敤鎴锋暟鎹洰褰曪細

```powershell
python scripts/manage_users.py delete --username user001
```

鍒犻櫎鐩綍鍓嶏紝鍚庣浼氭鏌ョ洰鏍囪矾寰勫繀椤讳綅浜?`DATA_DIR` 鍐咃紝閬垮厤璇垹涓嶅畨鍏ㄨ矾寰勩€?

## ???? Session

Web ???????? `contract_review_session` cookie ????????

??????????????????????????????????? `ctx`????? session ? `auth_contexts` ??

```text
auth_contexts[ctx] = {
  username,
  display_name,
  role
}
```

?????? URL ?? `ctx` ???? tab ???????

```text
/work?ctx=<ctx>
/history?ctx=<ctx>
/admin?ctx=<ctx>
```

????????????????????????? `ctx` ???????????????????

??????`POST /logout?ctx=<ctx>` ????? ctx??????????????? tab?

## Docker 閮ㄧ讲钀界偣

闇€瑕佸尯鍒嗗紑鍙戞満銆佽繙绔涓绘満銆佹鍦ㄨ繍琛岀殑鏈嶅姟瀹瑰櫒鍜屼复鏃剁鐞嗗鍣ㄣ€?

褰撳墠浠撳簱榛樿 `.env.example` 閰嶇疆锛?

```env
data/ and profiles/users.json
```

褰撳墠 `docker-compose.yaml` 鎸傝浇鍚庯紝瀹瑰櫒鍐呭疄闄呯瓑浠蜂簬锛?

```text
data/
profiles/users.json
```

compose 鎸傝浇锛?

```yaml
volumes:
  - ./profiles:/app/profiles
  - ./data:/app/data
```

姝ゆ椂 Web 鍚庡彴鍜?CLI 鍒涘缓鐢ㄦ埛鍚庯紝鏈€缁堝啓鍒拌繙绔涓绘満锛?

```text
./profiles/users.json
./data/<username>/
```

濡傛灉娌℃湁鎸傝浇 `DATA_DIR`锛岃繖浜涙暟鎹細鍐欒繘鏈嶅姟瀹瑰櫒鍐呴儴鏂囦欢绯荤粺锛屽鍣ㄩ噸寤哄悗鏈変涪澶遍闄┿€?

濡傛灉浠庢棫閮ㄧ讲杩佺Щ锛屽師鏉ョ殑 `users.json` 闇€瑕佹墜鍔ㄧЩ鍔ㄥ埌锛?

```text
profiles/users.json
```

濡傛灉甯屾湜璐﹀彿 JSON 鏀惧叆缁熶竴鏁版嵁鎸傝浇鐩綍锛屽彲浠ヨ缃細

```env
data/
profiles/users.json
```

骞舵妸 compose 璋冩暣涓哄彧鎸傝浇鎬绘暟鎹洰褰曪細

```yaml
volumes:
  - ./data:/app/data
```

濡傛灉瑕佽嚜瀹氫箟鏂扮敤鎴烽粯璁ゅ鏌ヨ鐐癸紝鍙互鎸傝浇鍗曚釜鏂囦欢锛?

```yaml
volumes:
  - ./data:/app/data
  - ./criteria.docx:/app/resources/criteria/criteria.docx:ro
```

杩欐牱鏂板缓鐢ㄦ埛鏃跺鍒跺嚭鏉ョ殑榛樿瀹℃煡瑕佺偣鏉ヨ嚜瀹夸富鏈烘枃浠躲€?

## 褰撳墠杈圭晫

褰撳墠鐢ㄦ埛绠＄悊浠嶆槸鍗曠鎴风敤鎴蜂綋绯伙細

- 鎵€鏈夌敤鎴峰叡浜竴涓?`USERS_FILE`銆?
- 鐢ㄦ埛涔嬮棿閫氳繃 `DATA_DIR/<username>` 鍒嗗尯銆?
- 绠＄悊鍛樻槸鍏ㄥ眬绠＄悊鍛橈紝涓嶆槸绉熸埛绠＄悊鍛樸€?
- 杩樻病鏈夌鎴疯〃鎴栫鎴风骇鏉冮檺妯″瀷銆?

鍚庣画杩涘叆绉熸埛闃舵鏃讹紝闇€瑕佹妸璐﹀彿鏁版嵁鍜岀洰褰曠粨鏋勬墿灞曚负绉熸埛鍒嗗尯锛屼緥濡傦細

```text
data/<tenant_id>/<username>/
```


## 当前路径配置

`DATA_DIR` 和 `USERS_FILE` 在 `config.py` 中固定为项目内的 `data/` 和 `profiles/users.json`。它们不再通过 `.env` 或 `config.yaml` 配置。
