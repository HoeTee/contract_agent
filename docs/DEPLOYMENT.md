# 閮ㄧ讲璇存槑

## 鏋勫缓闀滃儚

```powershell
docker build -t deep-research-agent:latest .
```

## 鍚姩鏈嶅姟

```powershell
docker compose up -d
```

## 鏈嶅姟鍣ㄤ笂蹇呴』鍑嗗鐨勬枃浠跺拰鐩綍

```text
.env
config.yaml
user_profiles/
data/
```

褰撳墠 `docker-compose.yaml` 浼氭妸 `.env`銆乣user_profiles/` 鍜?`data/` 鎸傝浇杩涘鍣細

```yaml
volumes:
  - ./.env:/app/.env:ro
  - ./config.yaml:/app/config.yaml:ro
  - ./user_profiles:/app/user_profiles
  - ./data:/app/data
```

`user_profiles/` 鍙互鏄┖鐩綍銆傞娆″垱寤虹敤鎴锋椂锛岀▼搴忎細鑷姩鐢熸垚锛?

```text
user_profiles/users.json
```

`user_profiles/` 闇€瑕佸彲鍐欐寕杞斤紝鍥犱负绠＄悊鍛樺悗鍙板拰 CLI 浼氬垱寤鸿处鍙凤紝鏅€氱敤鎴蜂篃鍙互鍦ㄥ墠绔慨鏀规樉绀哄悕绉般€?

鐢ㄦ埛杩愯鏁版嵁浼氳鎸傝浇鍒板鍣ㄤ腑锛?

```yaml
- ./data:/app/data
```

濡傛灉浠庢棫閮ㄧ讲杩佺Щ锛屽師鏉ョ殑 `users.json` 闇€瑕佹墜鍔ㄧЩ鍔ㄥ埌锛?

```text
user_profiles/users.json
```

`users_file` is no longer configurable in `config.yaml`; move legacy user data to `user_profiles/users.json`.
濡傛灉瑕佽嚜瀹氫箟鏂扮敤鎴烽粯璁ゅ鏌ヨ鐐规ā鏉匡紝鍙互鎸傝浇鍗曚釜鏂囦欢锛?

```yaml
- ./criteria.docx:/app/resources/review_criteria/criteria.docx:ro
```

涓嶈鎸傝浇绌虹殑 `resources/review_criteria/` 鐩綍瑕嗙洊瀹瑰櫒鍐呴粯璁ゆā鏉匡紝闄ら潪瀹夸富鏈虹洰褰曚腑宸茬粡鏈?`criteria.docx`銆?

## 绔彛璇存槑

褰撳墠 compose 鍛戒护璁╁鍣ㄥ唴閮ㄦ湇鍔＄洃鍚細

```text
0.0.0.0:8000
```

`docker-compose.yaml` 涓殑绔彛鏄犲皠鍐冲畾澶栭儴濡備綍璁块棶銆備緥濡傦細

```yaml
ports:
  - "0.0.0.0:5000:8000"
```

琛ㄧず鍏佽閫氳繃鏈嶅姟鍣?5000 绔彛璁块棶锛?

```text
http://鏈嶅姟鍣↖P:5000
```

濡傛灉鍙厑璁告湇鍔″櫒鏈満璁块棶锛岄渶瑕佹敼涓猴細

```yaml
ports:
  - "127.0.0.1:5000:8000"
```

鐒跺悗璁块棶锛?

```text
http://127.0.0.1:5000
```

## 鍋ュ悍妫€鏌?

```text
http://127.0.0.1:5000/health
```

瀹瑰櫒鍐呴儴鍋ュ悍妫€鏌ヨ闂殑鏄?`http://127.0.0.1:8000/health`锛岃繖鏄鍣ㄥ唴绔彛锛屼笉鏄涓绘満绔彛銆?
