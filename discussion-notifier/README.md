# Discussion Slack 알림

GitHub Discussion의 채널 알림과 개인 DM 알림을 설정하는 Lambda다. 대상 저장소는 `asm17-ms2/meterengine`이다.

## 알림 설정

1. Slack에서 `/discussion-notify`를 실행한다.
2. `내 DM 설정` 또는 `이 채널 설정`을 연다. 채널 설정은 해당 채널에서 명령을 실행하면 열린다.
3. `범위 추가`에서 저장소 전체, 카테고리, 특정 글 중 하나를 선택한다.
   - 카테고리: GitHub에 표시되는 카테고리 이름을 입력한다. 이름을 바꾸면 설정도 바꾼다.
   - 특정 글: 글 번호, `#123` 또는 이 저장소의 Discussion 링크를 입력한다.
4. 받을 이벤트를 선택하고 저장한다.
   - 새 글, 본문 수정, 제목 수정, 새 댓글, 새 답글, 댓글과 답글 수정, 답변 채택, 채택 취소, 닫힘, 재열림.
5. 알림을 끄려면 해당 범위의 이벤트를 모두 해제한다. 범위 자체를 지우려면 `이 범위 삭제`를 누른다.

- 채널 설정은 워크스페이스 팀원 누구나 변경한다. 개인 DM 설정은 각자 변경한다.
- 여러 범위가 겹치면 하나라도 켜진 이벤트를 한 번만 보낸다. 특정 글의 이벤트를 꺼도 저장소 전체 설정에서 켜져 있으면 받는다.
- 한 채널 또는 사용자당 범위는 최대 24개다. 같은 범위를 저장하면 기존 설정을 갱신한다.
- 알림의 `이 글 DM 알림` 버튼으로 해당 글의 이벤트를 바로 선택할 수 있다. 버튼을 누르는 것만으로 구독되지는 않는다.
- 채널 알림의 `채널 설정` 버튼으로 해당 채널의 공통 설정을 바로 연다.
- 채택 취소, 닫힘, 재열림은 기본 선택에서 제외된다. 받을 채널 또는 개인 DM의 범위 설정에서 각각 켠다. 기존 구독에도 자동으로 추가하지 않는다.
- 설정은 이후 들어오는 이벤트부터 적용된다. 지난 이벤트를 소급해서 보내지는 않는다.
- 봇이 발생시킨 이벤트, 삭제, 라벨, 고정, 잠금, 카테고리 변경은 보내지 않는다.

## 운영 배포

1. 변경을 PR로 검증하고 `main`에 병합한다.
2. GitHub Actions의 `Deploy Discussion notifier`에서 `Run workflow`를 누른다. 브랜치는 `main`을 선택한다.
3. 테스트가 통과하면 실행 Summary에서 변경할 리소스를 확인한다. 구체적인 변경은 `Plan production changes` 로그에서 확인한다.
4. 변경이 있으면 `production` 환경의 배포를 승인한다. 승인한 실행의 계획과 Lambda 패키지를 그대로 적용한다.
5. 배포 단계는 Lambda 2개의 코드 해시와 서명 없는 요청의 401 응답을 확인한다. Slack 알림을 발송하지 않는다.

- push만으로 운영 배포하지 않는다. 변경이 없으면 배포와 승인 단계도 건너뛴다.
- 기존 S3 상태 `discussion-notifier/terraform.tfstate`를 이어 쓴다. 설정이 그대로인 SQS와 DynamoDB는 재생성하지 않는다.
- 운영 상태가 없거나 삭제, 교체가 포함된 계획은 중단한다. 이런 변경은 별도 검토 후 로컬 Terraform으로 적용한다.
- 배포 권한과 GitHub 변수의 최초 설정은 [배포 설정](deploy/README.md)을 따른다.

## 테스트

Python 3.14, Terraform 1.16 이상이 필요하다. 테스트에서 AWS와 Slack에 전송하지 않는다.

```sh
uv run --no-project --python 3.14 --with-requirements lambda/requirements-test.txt \
  pytest -q -p no:cacheprovider -o pythonpath="$PWD/lambda" lambda/tests
uv run --no-project --python 3.14 --with-requirements lambda/requirements-test.txt \
  ruff check lambda
terraform -chdir=infra init -backend=false -lockfile=readonly
terraform -chdir=infra validate
terraform -chdir=infra test
```

## 기존 알림에서 전환

Slack 앱 설정 변경과 AWS 적용은 승인 뒤 실행한다. 아래 준비를 완료한 뒤 Lambda를 갱신한다.

1. 기존 알림 Slack 앱에 Bot Token Scopes `chat:write`, `commands`를 추가하고 워크스페이스에 다시 설치한다. 기존 Incoming Webhook은 유지한다.
   - 새 앱을 만들 경우 [slack-app-manifest.json](slack-app-manifest.json)을 예시로 쓴다. 두 URL 자리표시자를 실제 Function URL로 바꾼다.
   - Slash Command `/discussion-notify`의 Request URL과 Interactivity의 Request URL은 기존 Lambda Function URL로 지정한다.
   - 전송할 채널에 봇을 초대한다. 비공개 채널도 봇이 참여해야 한다.
2. Slack 앱의 Signing Secret과 Bot User OAuth Token을 SSM SecureString에 저장한다. Terraform은 이름만 참조하므로 비밀 값은 상태 파일에 들어가지 않는다.

   ```sh
   read -rs signing_secret
   aws ssm put-parameter --region ap-northeast-2 \
     --name /meterengine/discussion-notifier/slack-signing-secret \
     --type SecureString --value "$signing_secret"
   unset signing_secret
   read -rs bot_token
   aws ssm put-parameter --region ap-northeast-2 \
     --name /meterengine/discussion-notifier/slack-bot-token \
     --type SecureString --value "$bot_token"
   unset bot_token
   ```

3. [terraform.tfvars.example](infra/terraform.tfvars.example)과 [backend.s3.tfbackend.example](infra/backend.s3.tfbackend.example)을 복사한다. 예시의 AWS 계정 ID, Slack 워크스페이스와 채널 ID, 상태 버킷 이름을 실제 값으로 바꾼다. 복사한 운영 설정 파일은 Git에서 제외된다.

   ```sh
   cp infra/terraform.tfvars.example infra/terraform.tfvars
   cp infra/backend.s3.tfbackend.example infra/backend.s3.tfbackend
   ```

   - AWS 계정 ID는 12자리 숫자다. provider가 해당 계정으로만 배포를 허용한다.
   - Slack ID는 Slack URL과 채널 세부 정보에서 확인한다. 워크스페이스 ID는 `T`, 채널 ID는 `C` 또는 `G`로 시작한다.
   - 기존 배포를 갱신할 때는 기존 상태의 버킷과 key를 그대로 지정한다. 이 저장소는 실제 운영 값을 담지 않는다.

   값을 수정한 뒤 초기화하고 변경 계획을 확인한다.

   ```sh
   terraform -chdir=infra init -reconfigure -backend-config=backend.s3.tfbackend
   terraform -chdir=infra plan -out=discussion-notifier.plan
   terraform -chdir=infra apply discussion-notifier.plan
   ```

4. `/discussion-notify`로 기존 채널 설정을 연다. 처음 한 번만 새 글, 새 댓글, 새 답글, 답변 채택을 기본 등록한다. 수정 알림은 꺼진 상태로 시작한다. 이후 해제하거나 삭제한 설정은 재배포로 복원되지 않는다.
5. 개인 DM 범위를 등록하고 본문, 댓글, 답글을 수정해 선택한 사용자와 채널에만 알림이 오는지 확인한다. 수정 이벤트는 로컬 테스트로만 확인했으므로 실제 GitHub 페이로드도 이 단계에서 확인한다.
6. 콜드 스타트와 일반 호출 모두 Slack 응답 시간이 3초 이내인지 확인한다. Slack 설정 창과 버튼의 실제 표시는 이 단계에서 검수한다.

- 기존 Function URL과 GitHub 웹훅은 유지한다. 등록된 `discussion`, `discussion_comment` 이벤트가 수정도 전달하므로 `edited`를 별도로 웹훅에 등록하지 않는다.
- 기존 GitHub Slack 앱의 `discussions` 구독은 계속 끈 상태로 둔다. 중복 알림을 막기 위한 것이다.
- 기존 SSM `slack-webhook-url`은 롤백용으로 보관한다. 새 코드는 봇 API로 전송한다.
- 처음 배포하는 경우 운영 계정에 Terraform 상태 버킷을 만들고 GitHub 웹훅을 등록한다. 예시 설정은 리전 `ap-northeast-2`, key `discussion-notifier/terraform.tfstate`를 사용한다. GitHub 웹훅의 Secret은 SSM `/meterengine/discussion-notifier/github-webhook-secret` 값과 맞춘다.

## 처리와 운영

```text
GitHub 웹훅 -> 수신 Lambda -> SQS -> 전송 Lambda -> Slack 채널 / 개인 DM
Slack 명령, 버튼, 설정 창 -> 수신 Lambda -> DynamoDB 알림 설정
```

- GitHub HMAC 서명과 Slack 서명, 요청 시각을 검증한다. 설정한 저장소와 Slack 워크스페이스의 요청만 처리한다.
- DynamoDB는 구독 설정, 기본 채널 등록 여부, 전송 기록을 저장한다. 전송 기록만 7일 후 만료한다.
- SQS는 전송 실패를 재시도한다. 실패 수신자가 있어도 다른 수신자를 먼저 처리하고, 이미 성공한 수신자는 재시도에서 건너뛴다. 5회 처리해도 실패하면 별도 실패 큐에 남는다.
- 동일 이벤트의 여러 구독 조건은 수신자당 하나로 합친다. 중복 웹훅과 동시 처리에는 전송 기록과 120초 잠금을 사용한다.
- Slack 전송 성공 직후, 기록 저장 전에 프로세스가 종료되면 중복 전송할 수 있다. 외부 전송과 DynamoDB 기록을 하나의 트랜잭션으로 처리할 수 없으므로 완전한 1회 전송은 보장하지 않는다.
- 설정을 바꾸기 전에 큐에 들어온 이벤트도 처리 시점의 설정을 따른다.
- 알림은 이벤트와 작성자, 색상 테두리 카드, 글 번호와 제목, 본문, 저장소와 카테고리 순으로 표시한다. 수정, 채택과 취소, 닫힘과 재열림은 실행자와 원래 작성자를 구분한다. 닫힘과 재열림은 상태 안내를, 채택 취소는 이전 답변을 표시한다.
- 본문의 문단, 제목, 목록, 코드와 HTTP 링크를 Slack 서식으로 표시한다. 표는 행마다 `항목: 값`으로 풀어 쓴다. 본문은 변환된 서식 기준 최대 2,800자이며 넘으면 줄인다. 전문과 토의는 카드의 `GitHub에서 보기`로 연다.
- 로그에는 처리 결과, delivery ID 또는 오류 종류만 남긴다. 본문과 비밀 값은 남기지 않는다.
- 런타임은 `python3.14`의 boto3를 사용한다. 배포 런타임의 정확한 SDK 버전은 배포 후 확인한다. 로컬 검증 버전은 테스트 의존성 파일에 고정했다.

```sh
aws logs tail /aws/lambda/discussion-notifier --follow
aws logs tail /aws/lambda/discussion-notifier-worker --follow
terraform -chdir=infra output -raw failed_queue_url
```

- GitHub 수신 실패: Recent Deliveries에서 Redeliver한다.
- Slack 전송 실패: 전송 Lambda 로그와 실패 큐를 확인한다. `not_in_channel`이면 봇을 초대하고 재처리한다. 실패 큐의 재처리는 정상 전송도 발생시키므로 승인 후 실행한다.
- SSM 값을 바꾸면 5분 안에 반영된다. GitHub Secret을 바꾸면 웹훅도 같은 값으로 바꾼다.
- 롤백: 이전 코드와 Terraform 정의로 수신 Lambda를 복원한다. 전송 Lambda의 SQS 연결을 먼저 끄고 큐가 비었는지 확인해 새 전송과 이전 웹훅 전송이 겹치지 않게 한다. 구독 설정이 있는 DynamoDB는 삭제하지 않는다.

공식 문서: [GitHub 웹훅](https://docs.github.com/en/webhooks/webhook-events-and-payloads#discussion), [Slack 서명](https://docs.slack.dev/authentication/verifying-requests-from-slack/), [설정 창](https://docs.slack.dev/surfaces/modals/), [Slack 전송](https://docs.slack.dev/reference/methods/chat.postMessage/).
