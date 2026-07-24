<template>
  <v-text-field
    v-bind="$attrs"
    :type="inputType"
    :step="step"
    :reverse="reverse"
    :class="{ 'hide-controls': hideControls }"
    :model-value="displayValue"
    @update:model-value="onUpdate"
    @focus="onFocus"
    @blur="onBlur"
    @keydown.enter="onEnter"
    :rules="rules"
  />
</template>

<script setup>
import { computed, ref, useAttrs } from 'vue'
import { evaluateFormula } from '../utils/formula'

const attrs = useAttrs()

const props = defineProps({
  modelValue: {
    type: Number,
    default: null,
  },
  decimals: {
    type: Number,
    default: 2,
  },
  reverse: {
    type: Boolean,
    default: true,
  },
  hideControls: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const isFocused = ref(false)
const rawValue = ref('')
const lastFormula = ref(null)
const lastFormulaResult = ref(null)
const invalidFormula = ref(null)

const step = computed(() => (props.decimals === 0 ? '1' : (10 ** -props.decimals).toFixed(props.decimals)))
const inputType = computed(() => (isFocused.value || invalidFormula.value !== null ? 'text' : 'number'))

const rules = computed(() => {
  const parentRules = attrs.rules ? (Array.isArray(attrs.rules) ? attrs.rules : [attrs.rules]) : []
  return [...parentRules, () => invalidFormula.value === null || 'Ungültige Formel']
})

const displayValue = computed(() => {
  if (isFocused.value) return rawValue.value
  if (invalidFormula.value !== null) return 'NaN'
  const num = typeof props.modelValue === 'string' ? parseFloat(props.modelValue) : props.modelValue
  if (num === null || num === undefined || isNaN(num)) return props.modelValue
  return num.toFixed(props.decimals)
})

function onFocus() {
  isFocused.value = true
  if (invalidFormula.value !== null) {
    rawValue.value = invalidFormula.value
    invalidFormula.value = null
    return
  }
  if (lastFormula.value !== null && props.modelValue === lastFormulaResult.value) {
    rawValue.value = lastFormula.value
    return
  }
  rawValue.value = props.modelValue !== null && props.modelValue !== undefined ? String(props.modelValue) : ''
}

function onUpdate(val) {
  rawValue.value = val ?? ''
  const num = val === '' || val === null ? null : parseFloat(val)
  emit('update:modelValue', isNaN(num) ? null : num)
}

function onBlur() {
  isFocused.value = false
  const trimmed = rawValue.value.trim()
  if (trimmed.startsWith('=')) {
    try {
      const result = evaluateFormula(trimmed.slice(1))
      const rounded = parseFloat(result.toFixed(props.decimals))
      invalidFormula.value = null
      lastFormula.value = trimmed
      lastFormulaResult.value = rounded
      emit('update:modelValue', rounded)
    } catch {
      // invalid formula: keep it around (shown as NaN) so the user can come back and fix it
      invalidFormula.value = trimmed
    }
    return
  }
  invalidFormula.value = null
  lastFormula.value = null
  if (props.modelValue === null || props.modelValue === undefined) return
  const rounded = parseFloat(props.modelValue.toFixed(props.decimals))
  if (rounded !== props.modelValue) emit('update:modelValue', rounded)
}

function onEnter(event) {
  event.target.blur()
}
</script>

<script>
export default { inheritAttrs: false }
</script>

<style scoped>
.hide-controls :deep(input[type='number']::-webkit-inner-spin-button),
.hide-controls :deep(input[type='number']::-webkit-outer-spin-button) {
  -webkit-appearance: none;
  appearance: none;
}
.hide-controls :deep(input[type='number']) {
  -moz-appearance: textfield;
  appearance: textfield;
}
</style>
