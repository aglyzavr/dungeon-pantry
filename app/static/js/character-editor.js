/**
 * Factory function to create normalizer functions based on a schema template
 * Handles type conversion and default values for nested objects
 */
function createNormalizer(schema) {
  return function normalize(source) {
    const src = source || {};
    const result = {};

    for (const [key, template] of Object.entries(schema)) {
      // Handle nested objects recursively
      if (typeof template === 'object' && template !== null && !Array.isArray(template)) {
        result[key] = createNormalizer(template)(src[key]);
      }
      // Handle boolean values
      else if (typeof template === 'boolean') {
        result[key] = Boolean(src[key]);
      }
      // Handle string values (including string defaults like '0')
      else if (typeof template === 'string') {
        result[key] = String(src[key] ?? template);
      }
      // Handle other primitive values
      else {
        result[key] = src[key] ?? template;
      }
    }
    return result;
  };
}

/**
 * Schema defining the structure and default values for spell entries
 */
const spellSchema = {
  name: '',
  level: '0',
  attack_save: '',
  casting_time: '',
  range: '',
  components: '',
  duration: '',
  notes: '',
  bonus_action: false,
  crrm: {
    concentration: false,
    ritual: false,
  },
};

/**
 * Schema defining the structure and default values for attack entries
 */
const attackSchema = {
  name: '',
  atk_bonus_or_dc: '',
  damage_and_type: '',
  notes: '',
  bonus_action: false,
};

/**
 * Character Editor component for Alpine.js
 * Manages spell and attack entry management with data normalization
 */
window.CharacterEditor = {
  createNormalizer,

  /**
   * Normalizer function for spell entries
   */
  normalizeSpell: createNormalizer(spellSchema),

  /**
   * Normalizer function for attack entries
   */
  normalizeAttack: createNormalizer(attackSchema),

  /**
   * Factory function to create the Alpine.js component data object
   * @param {Array} spellData - Raw spell data from server
   * @param {Array} attackData - Raw attack data from server
   * @returns {Object} Alpine.js component data
   */
  getComponent(spellData, attackData) {
    return {
      activeTab: 'identity',

      spellEntries: (Array.isArray(spellData) ? spellData : []).map(
        this.normalizeSpell
      ),

      attackEntries: (Array.isArray(attackData) ? attackData : []).map(
        this.normalizeAttack
      ),

      /**
       * Add a new spell entry with normalized defaults
       */
      addSpell() {
        this.spellEntries.push(CharacterEditor.normalizeSpell({}));
      },

      /**
       * Remove a spell entry by index
       */
      removeSpell(index) {
        this.spellEntries.splice(index, 1);
      },

      /**
       * Add a new attack entry with normalized defaults
       */
      addAttack() {
        this.attackEntries.push(CharacterEditor.normalizeAttack({}));
      },

      /**
       * Remove an attack entry by index
       */
      removeAttack(index) {
        this.attackEntries.splice(index, 1);
      },
    };
  },
};
