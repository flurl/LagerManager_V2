<template>
  <v-text-field
    v-bind="$attrs"
    type="text"
    inputmode="decimal"
    :reverse="reverse"
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
import { formatNumber, formatNumberRaw, localeFromLanguage, parseNumber } from '../utils/number'
import { useAuthStore } from '../stores/auth'

const attrs = useAttrs()
const auth = useAuthStore()

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
  // Kept for call-site compatibility: the field is a text input, so it never has
  // spinner controls to hide.
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
// Input that could not be interpreted — kept verbatim so the user can come back and fix it.
const invalidInput = ref(null)
const invalidMessage = ref('')

const locale = computed(() => localeFromLanguage(auth.preferences?.language))

const rules = computed(() => {
  const parentRules = attrs.rules ? (Array.isArray(attrs.rules) ? attrs.rules : [attrs.rules]) : []
  return [...parentRules, () => invalidInput.value === null || invalidMessage.value]
})

const displayValue = computed(() => {
  if (isFocused.value) return rawValue.value
  if (invalidInput.value !== null) return 'NaN'
  const num = typeof props.modelValue === 'string' ? parseFloat(props.modelValue) : props.modelValue
  if (num === null || num === undefined || isNaN(num)) return props.modelValue
  return formatNumber(num, props.decimals, locale.value)
})

function onFocus() {
  isFocused.value = true
  if (invalidInput.value !== null) {
    rawValue.value = invalidInput.value
    invalidInput.value = null
    return
  }
  if (lastFormula.value !== null && props.modelValue === lastFormulaResult.value) {
    rawValue.value = lastFormula.value
    return
  }
  rawValue.value = formatNumberRaw(props.modelValue, locale.value)
}

function onUpdate(val) {
  rawValue.value = val ?? ''
  let num = null
  try {
    num = parseNumber(rawValue.value)
  } catch {
    // incomplete or malformed while typing — reported on blur
    num = null
  }
  emit('update:modelValue', num)
}

function onBlur() {
  isFocused.value = false
  const trimmed = rawValue.value.trim()
  if (trimmed.startsWith('=')) {
    try {
      const result = evaluateFormula(trimmed.slice(1))
      const rounded = parseFloat(result.toFixed(props.decimals))
      invalidInput.value = null
      lastFormula.value = trimmed
      lastFormulaResult.value = rounded
      emit('update:modelValue', rounded)
    } catch {
      invalidInput.value = trimmed
      invalidMessage.value = 'Ungültige Formel'
    }
    return
  }
  lastFormula.value = null
  try {
    const num = parseNumber(trimmed)
    invalidInput.value = null
    if (num === null) return
    const rounded = parseFloat(num.toFixed(props.decimals))
    if (rounded !== props.modelValue) emit('update:modelValue', rounded)
  } catch (e) {
    invalidInput.value = trimmed
    invalidMessage.value = e.message
  }
}

function onEnter(event) {
  event.target.blur()
}
</script>

<script>
export default { inheritAttrs: false }
</script>
