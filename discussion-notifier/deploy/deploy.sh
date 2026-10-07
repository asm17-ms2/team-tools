set -euo pipefail
umask 077

phase="${1:?Choose settings, plan, apply or cleanup}"
state_key="discussion-notifier/terraform.tfstate"
bundle_key="discussion-notifier/deploy-plans/${GITHUB_RUN_ID:?}/${GITHUB_RUN_ATTEMPT:?}-${GITHUB_SHA:?}.tgz"

if [[ "$phase" == "settings" ]]; then
  [[ "${GITHUB_REF:?}" == "refs/heads/main" ]] || exit 1
  for name in TF_VAR_aws_account_id TF_VAR_slack_team_id TF_VAR_default_channel_id STATE_BUCKET; do
    value="${!name:?Missing deployment variable}"
    printf '::add-mask::%s\n' "$value"
  done
  exit 0
fi

bundle_uri="s3://${STATE_BUCKET:?}/$bundle_key"
if [[ "$phase" == "cleanup" ]]; then
  aws s3 rm "$bundle_uri" --only-show-errors
  exit 0
fi

terraform -chdir=infra init -lockfile=readonly \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="key=$state_key" \
  -backend-config="region=$AWS_REGION" \
  -backend-config="use_lockfile=true"

if [[ "$phase" == "plan" ]]; then
  mkdir -p infra/build
  terraform -chdir=infra state pull > infra/build/state.json
  python3 deploy/plan.py state infra/build/state.json
  status=0
  terraform -chdir=infra plan -lock-timeout=60s -detailed-exitcode -out=deploy.plan || status=$?
  [[ "$status" == 0 || "$status" == 2 ]] || exit "$status"
  terraform -chdir=infra show -json deploy.plan > infra/build/plan.json
  python3 deploy/plan.py plan infra/build/plan.json
  if [[ "$status" == 0 ]]; then
    printf 'changes=false\n' >> "$GITHUB_OUTPUT"
    exit 0
  fi
  tar -czf infra/build/deploy.tgz -C infra deploy.plan build/lambda.zip
  aws s3 cp infra/build/deploy.tgz "$bundle_uri" --sse AES256 --only-show-errors
  printf 'changes=true\nbundle_sha256=%s\n' "$(shasum -a 256 infra/build/deploy.tgz | cut -d ' ' -f 1)" >> "$GITHUB_OUTPUT"
elif [[ "$phase" == "apply" ]]; then
  mkdir -p infra/build
  aws s3 cp "$bundle_uri" infra/build/deploy.tgz --only-show-errors
  printf '%s  %s\n' "${BUNDLE_SHA256:?}" infra/build/deploy.tgz | shasum -a 256 -c -
  tar -xzf infra/build/deploy.tgz -C infra deploy.plan build/lambda.zip
  terraform -chdir=infra apply -lock-timeout=60s deploy.plan
  expected="$(openssl dgst -sha256 -binary infra/build/lambda.zip | openssl base64 -A)"
  for function in discussion-notifier discussion-notifier-worker; do
    aws lambda wait function-updated-v2 --function-name "$function"
    actual="$(aws lambda get-function-configuration --function-name "$function" --query CodeSha256 --output text)"
    if [[ "$actual" != "$expected" ]]; then
      printf 'Code hash mismatch for %s: expected %s, got %s\n' "$function" "$expected" "$actual" >&2
      exit 1
    fi
  done
  url="$(terraform -chdir=infra output -raw function_url)"
  status="$(curl --silent --show-error --max-time 20 --output /dev/null --write-out '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{}' "$url")"
  if [[ "$status" != "401" ]]; then
    printf 'Unsigned request verification failed: expected HTTP 401, got %s\n' "$status" >&2
    exit 1
  fi
  printf '\nApplied commit `%s`. Both Lambda code hashes match; unsigned requests return 401.\n' "$GITHUB_SHA" >> "$GITHUB_STEP_SUMMARY"
else
  exit 1
fi
