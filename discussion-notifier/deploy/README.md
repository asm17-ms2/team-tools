# 수동 배포 설정

최초 한 번 AWS 관리 권한으로 배포 역할, Lambda 권한 상한 정책과 GitHub 설정을 준비한다. 이후 사용법은 [운영 배포](../README.md#운영-배포)를 따른다.

## AWS 역할

1. 운영 계정에 GitHub OIDC 공급자 `token.actions.githubusercontent.com`이 등록돼 있는지 확인한다. 이 정의는 기존 공급자를 조회하며 새로 만들지 않는다. 신뢰 조건은 조직과 저장소 ID가 포함된 OIDC 형식을 사용한다.
2. `infra/terraform.tfvars.example`과 `infra/backend.s3.tfbackend.example`을 복사하고 실제 값을 입력한다. 운영 Lambda 큐 연결의 UUID는 AWS Lambda 콘솔이나 운영 Terraform 상태에서 확인한다.
3. 같은 비공개 상태 버킷을 쓰되, 역할 설정의 key는 `team-tools/discussion-notifier-actions/terraform.tfstate`로 지정한다. 운영 리소스의 상태와 구분한다.

   ```sh
   cd discussion-notifier/deploy
   cp infra/terraform.tfvars.example infra/terraform.tfvars
   cp infra/backend.s3.tfbackend.example infra/backend.s3.tfbackend
   terraform -chdir=infra init -backend-config=backend.s3.tfbackend
   terraform -chdir=infra plan -out=actions.plan
   terraform -chdir=infra apply actions.plan
   ```

- `team-tools-discussion-plan`: `team-tools`의 `main`에서만 사용한다. 운영 리소스 조회, 상태 잠금, 배포 계획 보관 권한을 갖는다.
- `team-tools-discussion-deploy`: `team-tools`의 `production` 환경에서만 사용한다. 기존 운영 리소스와 상태 파일을 변경한다.
- 초기 설정은 역할 2개, 역할별 정책 2개와 `discussion-notifier-runtime-boundary` 정책 1개를 만든다. 권한 상한 정책은 운영 배포가 아닌 이 초기 설정에서 관리한다.
- 운영 배포는 Lambda 실행 역할에 권한 상한을 연결한다. 상한은 알림 로그 쓰기, SSM 비밀 3개 읽기, 설정 테이블 접근과 알림 큐 송수신을 허용한다. KMS 복호화는 SSM을 거쳐 지정된 비밀 3개를 읽는 경우와, Lambda 기본 키로 알림 Lambda 2개의 환경 변수를 읽는 경우에만 허용한다.
- Actions는 지정된 상한이 연결된 실행 역할의 정책을 수정할 수 있다. 상한 없이 역할을 만들거나 정책을 수정하는 작업, 상한의 변경과 제거, 실행 역할의 신뢰 정책 변경, 배포 역할 자체의 변경은 차단한다.
- 상한 확대와 신뢰 정책 변경은 AWS 관리 권한으로 별도 계획을 검토한 뒤 적용한다. 서비스 배포는 수동 Actions 하나를 계속 사용한다.
- Actions 역할에는 SSM 비밀을 직접 읽는 권한이 없다. Lambda 코드를 배포하면 실행 역할을 통해 지정된 비밀에 접근할 수 있으므로 배포 승인에는 이 접근 권한도 포함된다.
- 큐 연결을 교체했다면 `event_source_mapping_id`도 갱신하고 역할 계획을 다시 적용한다.

## GitHub 설정

`Settings > Secrets and variables > Actions > Variables`에 다음 저장소 변수를 등록한다. 실제 값은 코드에 넣지 않는다.

| 변수 | 값 |
| --- | --- |
| `NOTIFIER_AWS_ACCOUNT_ID` | 운영 AWS 계정 ID |
| `NOTIFIER_STATE_BUCKET` | 기존 운영 상태 버킷 이름 |
| `NOTIFIER_SLACK_TEAM_ID` | Slack 워크스페이스 ID |
| `NOTIFIER_CHANNEL_ID` | 기본 알림 채널 ID |
| `NOTIFIER_PLAN_ROLE_ARN` | 역할 설정의 `plan_role_arn` 출력 |

`Settings > Environments`에서 `production`을 만든다.

1. Required reviewers에 배포를 승인할 팀 관리자를 등록한다. 등록된 사람 중 1명의 승인이 필요하다.
2. Deployment branches and tags를 `main` 브랜치로 제한한다.
3. 환경 변수 `NOTIFIER_DEPLOY_ROLE_ARN`에 `deploy_role_arn` 출력을 등록한다.

AWS Access Key와 Slack 토큰은 GitHub에 등록하지 않는다. AWS 임시 인증에는 OIDC를 사용하고, Slack 토큰은 기존 SSM SecureString을 Lambda가 읽는다.

## 계획 보관과 실패 처리

- 계획과 Lambda ZIP은 기존 비공개 상태 버킷의 `discussion-notifier/deploy-plans/<실행 ID>/`에 암호화해서 저장한다. 공개 GitHub artifact로 올리지 않는다.
- 승인 뒤 같은 커밋을 체크아웃하고 패키지 SHA-256을 확인한다. 계획 작성 이후 운영 상태가 바뀌면 Terraform이 적용을 중단하므로 새 실행을 만든다.
- 적용 단계가 끝나면 보관한 패키지를 지운다. 승인 대기 중 실행을 취소한 경우에는 해당 실행 ID의 패키지가 남을 수 있다.
- 배포 실패 시 실행 로그를 먼저 확인한다. 상태를 지우거나 다른 key로 초기화하면 기존 리소스를 새로 만들려고 할 수 있으므로 운영 상태 key를 유지한다.

공식 문서: [OIDC와 AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [S3 상태와 잠금](https://developer.hashicorp.com/terraform/language/backend/s3).
