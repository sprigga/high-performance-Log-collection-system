#!/bin/bash
# 測試對照組監控系統

echo "=========================================="
echo "測試對照組監控系統"
echo "=========================================="

# 服務端點
FASTAPI_URL="http://localhost:18724"
METRICS_URL="http://localhost:18724/metrics"
PROMETHEUS_URL="http://localhost:19090"
GRAFANA_URL="http://localhost:13000"

echo ""
echo "1. 測試 FastAPI 服務..."
if curl -s "$FASTAPI_URL" > /dev/null; then
    echo "   ✅ FastAPI 服務正常"
else
    echo "   ❌ FastAPI 服務無回應"
fi

echo ""
echo "2. 測試 FastAPI 健康檢查..."
if curl -s "$FASTAPI_URL/health" > /dev/null; then
    echo "   ✅ 健康檢查端點正常"
    curl -s "$FASTAPI_URL/health" | python3 -m json.tool
else
    echo "   ❌ 健康檢查端點無回應"
fi

echo ""
echo "3. 測試 Prometheus Metrics 端點..."
if curl -s "$METRICS_URL" | grep -q "http_requests_total"; then
    echo "   ✅ Metrics 端點正常"
    echo "   可用指標數量: $(curl -s "$METRICS_URL" | grep -c "^[a-z]")"
else
    echo "   ❌ Metrics 端點無回應或格式錯誤"
fi

echo ""
echo "4. 測試 Prometheus 服務..."
if curl -s "$PROMETHEUS_URL/-/healthy" > /dev/null; then
    echo "   ✅ Prometheus 服務正常"
else
    echo "   ❌ Prometheus 服務無回應"
fi

echo ""
echo "5. 測試 Grafana 服務..."
if curl -s "$GRAFANA_URL/api/health" > /dev/null; then
    echo "   ✅ Grafana 服務正常"
else
    echo "   ❌ Grafana 服務無回應"
fi

echo ""
echo "6. 發送測試日誌..."
RESPONSE=$(curl -s -X POST "$FASTAPI_URL/api/log" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test-device-001",
    "log_level": "INFO",
    "message": "測試監控系統",
    "log_data": {"test": true}
  }')

if echo "$RESPONSE" | grep -q "saved"; then
    echo "   ✅ 日誌發送成功"
    echo "   回應: $RESPONSE"
else
    echo "   ❌ 日誌發送失敗"
    echo "   回應: $RESPONSE"
fi

echo ""
echo "7. 檢查 Metrics 更新..."
sleep 2
METRICS=$(curl -s "$METRICS_URL")
if echo "$METRICS" | grep -q "logs_received_total"; then
    echo "   ✅ 日誌指標已更新"
    echo "   logs_received_total:"
    echo "$METRICS" | grep "logs_received_total"
else
    echo "   ❌ 日誌指標未找到"
fi

echo ""
echo "=========================================="
echo "測試完成"
echo "=========================================="
echo ""
echo "訪問監控面板:"
echo "  • Grafana: $GRAFANA_URL (admin/admin)"
echo "  • Prometheus: $PROMETHEUS_URL"
echo ""
