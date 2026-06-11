/**
 * OPC-UA モックサーバー（テスト用）
 * node-opcua を使用してシンプルなOPC-UAサーバーを起動します。
 * ノード ns=1;i=1001〜1003 を1秒ごとにランダム値で更新します。
 *
 * 起動: node mock-server.js
 */

const { OPCUAServer, Variant, DataType, StatusCodes } = require("node-opcua");

async function startServer() {
  const server = new OPCUAServer({
    port: 4840,
    resourcePath: "/opcua/server",
    buildInfo: {
      productName: "MockOPCUAServer",
      buildNumber: "1",
      buildDate: new Date(),
    },
  });

  await server.initialize();

  const addressSpace = server.engine.addressSpace;
  const namespace = addressSpace.getOwnNamespace();

  // デバイスノードを追加
  const device = namespace.addObject({
    organizedBy: addressSpace.rootFolder.objects,
    browseName: "MockDevice",
  });

  // ノード定義
  const nodeConfigs = [
    { id: 1001, name: "Temperature", unit: "℃", base: 25.0, range: 5.0 },
    { id: 1002, name: "Pressure",    unit: "kPa", base: 101.3, range: 2.0 },
    { id: 1003, name: "FlowRate",    unit: "L/min", base: 50.0, range: 10.0 },
  ];

  const variables = nodeConfigs.map((cfg) => {
    let currentValue = cfg.base;
    return namespace.addVariable({
      componentOf: device,
      nodeId: `ns=1;i=${cfg.id}`,
      browseName: cfg.name,
      dataType: "Double",
      value: {
        get: () =>
          new Variant({ dataType: DataType.Double, value: currentValue }),
        set: (variant) => {
          currentValue = variant.value;
          return StatusCodes.Good;
        },
      },
    });
  });

  await server.start();
  console.log("✅ OPC-UA モックサーバー起動");
  console.log(`   エンドポイント: ${server.endpoints[0].endpointDescriptions()[0].endpointUrl}`);
  console.log("   監視ノード:");
  nodeConfigs.forEach((cfg) =>
    console.log(`     ns=1;i=${cfg.id}  (${cfg.name} [${cfg.unit}])`)
  );
  console.log("\n1秒ごとに値を更新中... Ctrl+C で停止");

  // 1秒ごとにランダムウォーク
  let tick = 0;
  setInterval(() => {
    tick++;
    nodeConfigs.forEach((cfg, idx) => {
      const delta = (Math.random() - 0.5) * cfg.range * 0.2;
      const node = variables[idx];
      const current = node.readValue().value.value;
      const next = Math.max(cfg.base - cfg.range, Math.min(cfg.base + cfg.range, current + delta));
      node.setValueFromSource(new Variant({ dataType: DataType.Double, value: next }));
    });
    if (tick % 10 === 0) {
      const vals = variables.map((v, i) =>
        `${nodeConfigs[i].name}: ${v.readValue().value.value.toFixed(2)}`
      );
      console.log(`[${new Date().toISOString()}] ${vals.join("  |  ")}`);
    }
  }, 1000);

  process.on("SIGINT", async () => {
    console.log("\nサーバーを停止中...");
    await server.shutdown();
    process.exit(0);
  });
}

startServer().catch(console.error);
