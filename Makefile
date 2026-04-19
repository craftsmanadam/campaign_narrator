# All our targets are phony (no files to check), so performance should increase if implicit rule search is skipped.
.PHONY: bootstrap clean analyze_code format build analyze_image unit_test integration_test watch_unit_tests acceptance_test test verify start stop run_local clear_state stop_local

bootstrap:
	./bin/bootstrap.sh
clean:
	./bin/clean.sh
analyze_code: bootstrap
	./bin/analyze_code.sh
format:
	./bin/format.sh
build: bootstrap
	./bin/build.sh
analyze_image: build
	./bin/analyze_image.sh
unit_test: bootstrap
	./bin/unit_tests.sh
integration_test: bootstrap
	./bin/integration_tests.sh
watch_unit_tests: bootstrap
	./bin/watch_unit_tests.sh
acceptance_test: bootstrap
	./bin/acceptance_tests.sh
test: unit_test integration_test acceptance_test
verify: clean analyze_code unit_test integration_test acceptance_test
start: build
	./bin/start.sh
stop:
	./bin/stop.sh
run_local: bootstrap
	./bin/run_local.sh $(ARGS)
clear_state:
	./bin/clear_state.sh
stop_local:
	./bin/stop_local.sh
