/**
 * Base class for AI providers. Implement `generateJson` in each provider subclass.
 */
export class AiProvider {
  /**
   * Submit attachments and a prompt to the AI and return the raw JSON string.
   *
   * @param {object} params
   * @param {string[]} params.attachmentUrls - Public URLs of files to include (images/PDFs)
   * @param {string}   params.prompt         - The text prompt to send
   * @returns {Promise<string>} Raw JSON string returned by the model
   */
  // eslint-disable-next-line no-unused-vars
  async generateJson({ attachmentUrls, prompt }) {
    throw new Error(`${this.constructor.name} does not implement generateJson()`)
  }
}
