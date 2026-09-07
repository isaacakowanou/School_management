export function resetPasswordErrorMessage(error, t) {
  if (error?.code === 'invalid_reset_link') {
    return t('forgotPassword.invalidResetLink')
  }
  return error?.message || t('forgotPassword.resetError')
}
