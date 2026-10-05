# Team tools

팀에서 사용하는 작은 자동화 도구의 코드와 배포 설정을 모은다. 도구별 사용법과 운영 절차는 각 디렉터리의 README에서 확인한다.

| 도구 | 하는 일 | 사용법 |
| --- | --- | --- |
| Discussion 알림 | GitHub Discussion의 채널 알림과 개인 DM을 범위, 이벤트별로 설정한다 | [discussion-notifier](discussion-notifier/README.md) |

## 개발

```sh
cd discussion-notifier
uv run --no-project --python 3.14 --with-requirements lambda/requirements-test.txt \
  pytest -q -p no:cacheprovider -o pythonpath="$PWD/lambda" lambda/tests
```

- 도구마다 별도 디렉터리에 코드, 테스트, 인프라 정의를 둔다.
- 비밀 값, 실제 배포 계정과 상태 버킷 설정, Terraform 상태는 저장소에 넣지 않는다. 설정 예시와 적용 방법은 각 도구의 README에서 확인한다.
- push와 PR에서는 테스트와 Terraform 검증을 실행한다. Discussion 알림은 [수동 Actions 배포](discussion-notifier/README.md#운영-배포)를 사용한다.
