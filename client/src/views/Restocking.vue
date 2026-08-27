<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <label class="budget-label">{{ t('restocking.budgetLabel') }}</label>
        <div class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        <input
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          step="500"
          v-model.number="budget"
        />
        <div class="budget-scale">
          <span>{{ formatCurrency(0, currentCurrency) }}</span>
          <span>{{ formatCurrency(maxBudget, currentCurrency) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.recommendedSpend') }}</div>
          <div class="stat-value">{{ formatCurrency(totalSpend, currentCurrency) }}</div>
        </div>
        <div class="stat-card" :class="budgetRemaining < 0 ? 'danger' : 'success'">
          <div class="stat-label">{{ t('restocking.budgetRemaining') }}</div>
          <div class="stat-value">{{ formatCurrency(budgetRemaining, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemCount') }}</div>
          <div class="stat-value">{{ itemCount }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ longestLeadTime }} {{ t('restocking.days') }}</div>
        </div>
      </div>

      <div v-if="placedOrder" class="success-panel">
        <div class="success-text">
          {{ t('restocking.orderPlaced', { orderNumber: placedOrder.order_number }) }}
        </div>
        <router-link to="/orders" class="success-link">
          {{ t('restocking.viewInOrders') }}
        </router-link>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationsTitle') }}</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-recs">
          {{ t('restocking.noRecommendations') }}
        </div>

        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in recommendations" :key="row.item_sku">
                <td><strong>{{ row.item_sku }}</strong></td>
                <td>{{ row.item_name }}</td>
                <td>
                  {{ row.quantity }}
                  <span v-if="row.partial" class="partial-tag">{{ t('restocking.partialFill') }}</span>
                </td>
                <td>{{ formatCurrency(row.unit_cost, currentCurrency) }}</td>
                <td>{{ formatCurrency(row.lineTotal, currentCurrency) }}</td>
                <td>{{ row.lead_time_days }} {{ t('restocking.days') }}</td>
                <td><span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="actions">
          <button
            class="place-order-btn"
            :disabled="submitting || recommendations.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const placedOrder = ref(null)

    const gapItems = computed(() => {
      return forecasts.value
        .map(f => ({
          item_sku: f.item_sku,
          item_name: f.item_name,
          unit_cost: f.unit_cost,
          lead_time_days: f.lead_time_days,
          trend: f.trend,
          gap: f.forecasted_demand - f.current_demand
        }))
        .filter(item => item.gap > 0)
    })

    const maxBudget = computed(() => {
      if (gapItems.value.length === 0) return 1000
      const total = gapItems.value.reduce((sum, i) => sum + i.gap * i.unit_cost, 0)
      return Math.ceil(total / 500) * 500
    })

    const minBudget = computed(() => 0)

    const recommendations = computed(() => {
      const sorted = [...gapItems.value].sort((a, b) => {
        const aInc = a.trend === 'increasing' ? 0 : 1
        const bInc = b.trend === 'increasing' ? 0 : 1
        if (aInc !== bInc) return aInc - bInc
        return b.gap - a.gap
      })

      const rows = []
      let spent = 0
      for (const item of sorted) {
        const fullCost = item.gap * item.unit_cost
        if (spent + fullCost <= budget.value) {
          rows.push(buildRow(item, item.gap, false))
          spent += fullCost
        } else {
          const qty = Math.floor((budget.value - spent) / item.unit_cost)
          if (qty >= 1) {
            rows.push(buildRow(item, qty, true))
            spent += qty * item.unit_cost
          }
          break
        }
      }
      return rows
    })

    const buildRow = (item, quantity, partial) => ({
      item_sku: item.item_sku,
      item_name: item.item_name,
      quantity,
      unit_cost: item.unit_cost,
      lineTotal: quantity * item.unit_cost,
      lead_time_days: item.lead_time_days,
      trend: item.trend,
      partial
    })

    const totalSpend = computed(() =>
      recommendations.value.reduce((sum, r) => sum + r.lineTotal, 0)
    )
    const budgetRemaining = computed(() => budget.value - totalSpend.value)
    const itemCount = computed(() => recommendations.value.length)
    const longestLeadTime = computed(() =>
      recommendations.value.reduce((max, r) => Math.max(max, r.lead_time_days), 0)
    )

    watch(forecasts, () => {
      budget.value = Math.round((maxBudget.value * 0.6) / 500) * 500
    })

    const placeOrder = async () => {
      submitting.value = true
      error.value = null
      try {
        const result = await api.createRestockOrder({
          budget: budget.value,
          items: recommendations.value.map(r => ({
            item_sku: r.item_sku,
            item_name: r.item_name,
            quantity: r.quantity,
            unit_cost: r.unit_cost,
            lead_time_days: r.lead_time_days
          }))
        })
        placedOrder.value = result
      } catch (err) {
        error.value = 'Failed to place order: ' + (err.response?.data?.detail || err.message)
      } finally {
        submitting.value = false
      }
    }

    onMounted(async () => {
      try {
        loading.value = true
        forecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    })

    return {
      t,
      currentCurrency: computed(() => currentCurrency.value),
      formatCurrency,
      loading,
      error,
      budget,
      submitting,
      placedOrder,
      maxBudget,
      minBudget,
      recommendations,
      totalSpend,
      budgetRemaining,
      itemCount,
      longestLeadTime,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  accent-color: #2563eb;
  height: 6px;
  border-radius: 3px;
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #64748b;
}

.partial-tag {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  background: #fed7aa;
  color: #92400e;
  font-size: 0.688rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.empty-recs {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.actions {
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}

.place-order-btn {
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.success-panel {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.success-text {
  color: #065f46;
  font-weight: 600;
  font-size: 0.938rem;
}

.success-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: none;
  font-size: 0.875rem;
}

.success-link:hover {
  text-decoration: underline;
}
</style>
