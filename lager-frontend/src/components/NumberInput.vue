<template>
  <v-text-field
    v-bind="$attrs"
    type="number"
    :step="step"
    :reverse="reverse"
    :class="{ 'hide-controls': hideControls }"
    :model-value="displayValue"
    @update:model-value="onUpdate"
    @focus="onFocus"
    @blur="onBlur"
  />
</template>

<script setup>
import { computed, ref } from 'vue'

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

const step = computed(() => (props.decimals === 0 ? '1' : (10 ** -props.decimals).toFixed(props.decimals)))

const displayValue = computed(() => {
  if (isFocused.value) return rawValue.value
  const num = typeof props.modelValue === 'string' ? parseFloat(props.modelValue) : props.modelValue
  if (num === null || num === undefined || isNaN(num)) return props.modelValue
  return num.toFixed(props.decimals)
})

function onFocus() {
  isFocused.value = true
  rawValue.value = props.modelValue !== null && props.modelValue !== undefined ? String(props.modelValue) : ''
}

function onUpdate(val) {
  rawValue.value = val ?? ''
  const num = val === '' || val === null ? null : parseFloat(val)
  emit('update:modelValue', isNaN(num) ? null : num)
}

function onBlur() {
  isFocused.value = false
  if (props.modelValue === null || props.modelValue === undefined) return
  const rounded = parseFloat(props.modelValue.toFixed(props.decimals))
  if (rounded !== props.modelValue) emit('update:modelValue', rounded)
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
