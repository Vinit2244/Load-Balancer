PROTO_DIR=proto
OUT_DIR=generated
LB_PORT=50051

# Allow overriding of certain cmd line args
INTERVAL ?= 10
POLICY ?= rr
WORKERS ?= 3
BASE_PORT ?= 50052

# Find all .proto files in the proto directory
PROTO_FILES=$(wildcard $(PROTO_DIR)/*.proto)
GENERATED_FILES=$(PROTO_FILES:$(PROTO_DIR)/%.proto=$(OUT_DIR)/%_pb2.py)

all: compile

compile: $(GENERATED_FILES)

$(OUT_DIR)/%_pb2.py: $(PROTO_DIR)/%.proto
	python3 -m grpc_tools.protoc --proto_path=$(PROTO_DIR) --python_out=$(OUT_DIR) --grpc_python_out=$(OUT_DIR) $<

consul:
	consul agent -dev

lb:
	python3 server/lb.py --port=$(LB_PORT) --interval=$(INTERVAL) --policy=$(POLICY)

workers:
	@for i in $(shell seq 1 $(WORKERS)); do \
		port=$$(($(BASE_PORT) + $$i)); \
		echo "Starting worker $$i on port $$port"; \
		python3 server/worker.py --port $$port --id $$i --interval $(INTERVAL); \
	done
	
run_client:
	python3 client/client.py

clean:
	rm -rf $(OUT_DIR)/*_pb2.py*
	rm -rf $(OUT_DIR)/*_pb2_grpc.py*
	find . -name "__pycache__" -type d -exec rm -rf {} +
	rm -rf ./server/logs/*.log
	rm -rf ./server/*.json