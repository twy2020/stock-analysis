<script setup lang="ts">
import TicketInbox from './feedback/TicketInbox.vue'
import '../styles/message-center.css'
withDefaults(defineProps<{feedbackId?:string;active?:boolean}>(),{active:true})
const emit=defineEmits<{updated:[]}>()
</script>
<template><section class="feedback-admin"><TicketInbox admin :ticket-id="feedbackId" :active="active" @updated="emit('updated')"/></section></template>
