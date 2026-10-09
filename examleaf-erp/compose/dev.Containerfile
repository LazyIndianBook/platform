# syntax=docker/dockerfile:1.7
# The development image: frappe/erpnext:v16.50.0 (frappe_docker's production image; never `latest`, which is develop)
# plus India Compliance v16.10.0, fetched and built the way bench installs any app. examleaf_erp is not copied in:
# compose.yaml mounts this repository's copy at apps/examleaf_erp in every container, and the .pth below puts it on
# their Python path, so an edit in the repository is live (bench migrate for schema changes). Production builds a
# sealed image instead: ../image/build.sh.
FROM frappe/erpnext:v16.50.0

ARG INDIA_COMPLIANCE_REF=v16.10.0
USER frappe
WORKDIR /home/frappe/frappe-bench

# The image keeps its built assets in ./assets (the entrypoint links them into the sites volume at start): link them
# for the build so India Compliance's bundles land there, then take the link away again.
RUN ln -s /home/frappe/frappe-bench/assets sites/assets \
 && bench get-app --branch "${INDIA_COMPLIANCE_REF}" https://github.com/resilient-tech/india-compliance \
 && rm sites/assets \
 && rm -rf apps/india_compliance/node_modules /home/frappe/.cache/yarn \
 && echo /home/frappe/frappe-bench/apps/examleaf_erp > env/lib/python3.14/site-packages/examleaf_erp.pth
